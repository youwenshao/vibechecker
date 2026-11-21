"""Audit frozen development paraphrases against their publisher parents and numeric scoring stages."""

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import joblib
import numpy as np
from scipy.special import expit
from threadpoolctl import threadpool_limits

from .deep_runner import write_json
from .loaders import Example, fingerprint, partition
from .refit import CachedRow, append_probe, load_rows
from .refit_cache import CALIBRATION, TRAIN, VALIDATION, role
from .registry import registry, sha256
from .rewrite_data import load_rewrite_pairs

NAMES = {TRAIN: "stack", CALIBRATION: "calibration", VALIDATION: "validation"}
ORIGINS = ("human", "machine")
REFUSAL = re.compile(
    r"\b(?:as an ai(?: language model| assistant)?|i(?: am|'m) (?:sorry|unable)|"
    r"i (?:cannot|can't) (?:assist|provide|help|fulfill|comply))\b",
    re.IGNORECASE,
)


def distribution(values):
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError("Expected finite observations")
    return dict(
        zip(
            ("min", "p10", "median", "p90", "max"),
            map(float, np.quantile(values, [0, 0.1, 0.5, 0.9, 1])),
            strict=True,
        )
    )


def similarities(left, right):
    """Case-folded token-sequence edit ratio and contiguous 5-token Jaccard similarity."""
    left, right = (s.casefold().split() for s in (left, right))

    def shingles(tokens):
        return {tuple(tokens[i : i + 5]) for i in range(len(tokens) - 4)}

    a, b = shingles(left), shingles(right)
    return (
        SequenceMatcher(None, left, right, autojunk=False).ratio(),
        len(a & b) / len(a | b) if a or b else float(left == right),
    )


def integrity(rows):
    from vibechecker_engine.text import Refusal, prepare, validate

    counts, similarities_to, normalization_flags = (
        Counter(application_refusals=0),
        defaultdict(list),
        Counter(),
    )
    for item, native, parent, human in rows:
        counts["documents"] += 1
        doc = prepare(native["generation"])
        if item.id != fingerprint(native["generation"]):
            raise ValueError("Selected document does not match the native publisher text")
        counts["word_count_disagrees_with_cache"] += item.words != doc.word_count
        counts["label_disagrees_with_publisher"] += item.label != int(native["model"] != "human")
        counts["native_text_changes_under_engine_normalization"] += (
            doc.normalized != native["generation"]
        )
        counts["normalized_fingerprint_changes_after_engine_normalization"] += (
            fingerprint(doc.normalized) != item.id
        )
        counts["contains_refusal_phrase_in_first_250_characters"] += bool(
            REFUSAL.search(doc.normalized[:250])
        )
        normalization_flags.update(doc.flags)
        try:
            validate(doc, "deep")
        except Refusal as exc:
            counts["application_refusals"] += 1
            counts["application_refusal/" + exc.code] += 1
        for name, other in (("to_clean_same_origin", parent), ("to_native_human", human)):
            if other is None:
                counts["missing_" + name] += 1
                continue
            distance = similarities(native["generation"], other["generation"])
            counts["exact_text_" + name] += native["generation"] == other["generation"]
            counts["exact_normalized_" + name] += item.id == fingerprint(other["generation"])
            counts["near_" + name] += distance[0] >= 0.9 or distance[1] >= 0.8
            similarities_to[name].append(distance)
        if parent is not None:
            counts["native_parent_id_correct"] += native["adv_source_id"] == parent["id"]
            counts["parent_model_correct"] += native["model"] == parent["model"]
            counts["parent_source_correct"] += native["source_id"] == parent["source_id"]
        if parent is not None and human is not None:
            distance = similarities(parent["generation"], human["generation"])
            counts["parent_exact_normalized_to_native_human"] += fingerprint(
                parent["generation"]
            ) == fingerprint(human["generation"])
            counts["parent_near_native_human"] += distance[0] >= 0.9 or distance[1] >= 0.8
            similarities_to["parent_to_native_human"].append(distance)
    return {
        "counts": dict(counts),
        "input_flags": dict(normalization_flags),
        "similarity": {
            k: {
                "token_sequence_ratio": distribution(np.asarray(v)[:, 0]),
                "five_token_jaccard": distribution(np.asarray(v)[:, 1]),
            }
            for k, v in similarities_to.items()
        },
    }


def native_academic(rows, cache):
    """Map only allowed, pre-existing training/calibration/development IDs to publisher passages."""
    import pyarrow.dataset as ds
    from pyarrow import csv

    catalog = registry()
    clean_art, attack_art = (catalog[k].artifacts[0] for k in ("raid", "raid-attacks"))
    clean_path, attack_path = (cache / a.sha256 for a in (clean_art, attack_art))
    if sha256(clean_path) != clean_art.sha256 or sha256(attack_path) != attack_art.sha256:
        raise ValueError("Native publisher byte identity mismatch")
    attacks = ds.dataset(attack_path, format="parquet")
    # Scan source identifiers alone to recover the frozen cache's one-way group mapping.
    source_keys = set(attacks.to_table(columns=["source_id"]).column(0).unique().to_pylist())
    wanted = {r.group: r.role for r in rows}
    allowed = {}
    for key in source_keys:
        raw = "raid:" + key
        group = fingerprint(raw)
        if group not in wanted:
            continue
        dummy = Example("", 0, "raid-attacks", partition(raw), "other", source_group=raw)
        if role(dummy) != wanted[group]:
            raise ValueError("Source is outside the permitted training/calibration/validation role")
        allowed[key] = group
    if set(allowed.values()) != wanted.keys():
        raise ValueError("Missing native publisher source identifier")
    cols = ["id", "source_id", "adv_source_id", "domain", "model", "generation", "attack"]
    scoped = ds.field("source_id").isin(list(allowed))
    native = defaultdict(list)
    for d in attacks.to_table(
        columns=cols, filter=scoped & (ds.field("attack") == "paraphrase")
    ).to_pylist():
        native[fingerprint(d["generation"])].append(d)
    selected = []
    for r in rows:
        found = [
            d
            for d in native[r.id]
            if allowed[d["source_id"]] == r.group and int(d["model"] != "human") == r.label
        ]
        if len(found) != 1:
            raise ValueError(
                "Expected one native paraphrase matching selected document, label and source"
            )
        selected.append((r, found[0]))
    parent_ids = {d["adv_source_id"] for _, d in selected}
    clean = ds.dataset(
        clean_path,
        format=ds.CsvFileFormat(
            parse_options=csv.ParseOptions(newlines_in_values=True),
            read_options=csv.ReadOptions(block_size=2**24),
        ),
    )
    clean_filter = (
        scoped
        & (ds.field("attack") == "none")
        & (ds.field("id").isin(sorted(parent_ids)) | (ds.field("model") == "human"))
    )
    parents, humans = {}, {}
    for d in clean.to_table(
        columns=["id", "source_id", "domain", "model", "generation"], filter=clean_filter
    ).to_pylist():
        parents[d["id"]] = d
        if d["model"] == "human":
            if d["source_id"] in humans:
                raise ValueError("Ambiguous human parent")
            humans[d["source_id"]] = d
    groups = defaultdict(list)
    for r, d in selected:
        groups[NAMES[r.role] + "/" + d["domain"] + "/" + ORIGINS[r.label]].append(
            (r, d, parents.get(d["adv_source_id"]), humans.get(d["source_id"]))
        )
    return {k: integrity(v) for k, v in sorted(groups.items())}


def stages(stacker, probe, rows):
    from vibechecker_engine.stacker import length_bin

    x = append_probe(
        np.stack([r.features for r in rows]), np.stack([r.encoder for r in rows]), probe
    )
    classifier = stacker.classifier
    raw = classifier.predict_proba(x)[:, 1]
    calibrated = np.asarray(
        [
            stacker.calibrators.get(length_bin(r.words), stacker.calibrators["pooled"]).point(p)
            for r, p in zip(rows, raw, strict=True)
        ]
    )
    y = np.asarray([r.label for r in rows])

    def summary(v):
        return {
            **distribution(v),
            "mean": float(np.mean(v)),
            "exact_zero": int(sum(v == 0)),
            "exact_one": int(sum(v == 1)),
            "unique": len(np.unique(v)),
            "below_0_01": int(sum(v < 0.01)),
            "above_0_99": int(sum(v > 0.99)),
            "brier": float(np.mean((v - y) ** 2)),
        }

    return {
        "documents": len(rows),
        "groups": len({r.group for r in rows}),
        "at_or_above_half": int(np.sum(np.rint(100 * calibrated) >= 50)),
        "high_band": {
            "index_threshold": stacker.high_threshold,
            "hits": int(np.sum(np.rint(100 * calibrated) >= stacker.high_threshold)),
        },
        "calibration_curves": dict(
            Counter(
                length_bin(r.words) if length_bin(r.words) in stacker.calibrators else "pooled"
                for r in rows
            )
        ),
        "probe": summary(x[:, -1]),
        "tree": summary(expit(classifier.estimator.decision_function(x))),
        "anchored_before_isotonic": summary(raw),
        "isotonic": summary(calibrated),
        "displayed": summary(np.rint(100 * calibrated) / 100),
    }


def curve_support(stacker):
    def summarize(calibration):
        x, y = calibration.point.x, calibration.point.y
        zero, one = x[y == 0], x[y == 1]
        return {
            "raw_min": float(x[0]),
            "raw_max": float(x[-1]),
            "first_isotonic_value": float(y[0]),
            "last_isotonic_value": float(y[-1]),
            "largest_knot_scored_zero": float(zero.max()) if len(zero) else None,
            "smallest_knot_scored_one": float(one.min()) if len(one) else None,
            "knots": len(x),
            "distinct_isotonic_levels": len(np.unique(y)),
            "bootstraps": len(calibration.bootstrap),
        }

    return {k: summarize(calibration) for k, calibration in stacker.calibrators.items()}


def effective_training(cache, rows, selection):
    """Recover the prior fit's exact nine excluded memberships without opening final passages."""
    from itertools import combinations

    import pyarrow.dataset as ds
    from pyarrow import csv

    from .refit_cache import digest_strings

    clean = cache / registry()["raid"].artifacts[0].sha256
    table = ds.dataset(
        clean,
        format=ds.CsvFileFormat(
            parse_options=csv.ParseOptions(newlines_in_values=True),
            read_options=csv.ReadOptions(block_size=2**24),
        ),
    )
    human = (ds.field("model") == "human") & (ds.field("attack") == "none")
    all_source_ids = (
        table.to_table(columns=["source_id"], filter=human).column(0).unique().to_pylist()
    )
    validation_source_ids = {r.group for r in rows[VALIDATION]}
    allowed = [
        k
        for k in all_source_ids
        if partition("raid:" + k) in ("train", "calibration")
        or fingerprint("raid:" + k) in validation_source_ids
    ]
    hashes = defaultdict(set)
    for batch in table.scanner(
        columns=["source_id", "generation"], filter=human & ds.field("source_id").isin(allowed)
    ).to_batches():
        for d in batch.to_pylist():
            hashes[fingerprint(d["generation"])].add(fingerprint("raid:" + d["source_id"]))
    known = {g for values in hashes.values() if len(values) > 1 for g in values}
    original = selection["source_quarantine"]
    effective = {}
    for part in (TRAIN, CALIBRATION):
        wanted = original["excluded"][NAMES[part] if part == CALIBRATION else "train"]
        available = {r.group for r in rows[part]}
        certain = known & available
        missing = wanted["groups"] - len(certain)
        if not 0 <= missing <= 2:
            raise ValueError(
                f"Cannot reproduce frozen quarantine from allowed roles: role {part}, missing {missing}"
            )
        # The original release committed the excluded group set as a single digest.
        # At most two unmatched groups can be recovered by testing membership keys alone.
        matched = next(
            (
                certain.union(more)
                for more in combinations(sorted(available - certain), missing)
                if digest_strings(sorted(certain.union(more))) == wanted["group_ids_sha256"]
            ),
            None,
        )
        if matched is None:
            raise ValueError(
                "Frozen group exclusion commitment does not match permitted membership"
            )
        removed = [r for r in rows[part] if r.group in matched]
        if digest_strings(sorted(r.id for r in removed)) != wanted["document_ids_sha256"]:
            raise ValueError("Frozen document exclusion commitment differs")
        effective[part] = [r for r in rows[part] if r.group not in matched]
    effective[VALIDATION] = rows[VALIDATION]
    if (
        digest_strings(
            sorted(
                f"{r.id} {r.group} {r.role} {r.label} {r.words}"
                for part in effective.values()
                for r in part
            )
        )
        != original["effective_selection_sha256"]
    ):
        raise ValueError("Recovered effective memberships differ from the frozen v2/v3 fit")
    return effective


def challenger_ranges(effective, groups, source_rows, probes, selection, names):
    from vibechecker_engine.deep import ProbeDeepStacker

    from .refit import validation_quality
    from .rewrite_refit import displayed, stress_metrics

    extra = defaultdict(list)
    domains = {}
    for group, values in groups.items():
        if group.startswith("matched/"):
            _, part, domain, _ = group.split("/")
            extra[part].extend(values)
            domains.update({r.group: domain for r in values})
    for part in extra:
        extra[part].sort(key=lambda r: (domains[r.group], r.group, r.id))
    by_part = {
        TRAIN: [*effective[TRAIN], *extra["stack"]],
        CALIBRATION: [*effective[CALIBRATION], *extra["calibration"]],
        VALIDATION: effective[VALIDATION],
        3: extra["stress"],
    }
    y = {k: np.asarray([r.label for r in v]) for k, v in by_part.items()}
    results, curves = {}, {}
    for kind, probe in probes.items():
        matrix = {
            k: append_probe(
                np.stack([r.features for r in v]), np.stack([r.encoder for r in v]), probe
            )
            for k, v in by_part.items()
        }
        for anchor in (0.5, 0.75):
            tag = f"{kind}-anchor{anchor:g}"
            reference = selection["candidates"][tag]
            fitted = ProbeDeepStacker.fit(
                matrix[TRAIN],
                y[TRAIN],
                matrix[CALIBRATION],
                y[CALIBRATION],
                [r.words for r in by_part[CALIBRATION]],
                seed=selection["protocol"]["seed"],
                max_leaf_nodes=7,
                l2_regularization=1.0,
                probe_anchor=anchor,
            )
            fitted.high_threshold = round(100 * reference["ordinary"]["thresholds"]["high"])
            quality = validation_quality(fitted, matrix[VALIDATION], by_part[VALIDATION], names)
            stress = stress_metrics(displayed(fitted, matrix[3], by_part[3]), by_part[3], domains)
            if (
                quality["metrics"] != reference["ordinary"]["metrics"]
                or stress != reference["stress"]
            ):
                raise ValueError(
                    "CPU replay does not reproduce all frozen validation/stress metrics"
                )
            results[tag] = {k: stages(fitted, probe, v) for k, v in source_rows.items()}
            curves[tag] = curve_support(fitted)
    return results, curves


def academic_groups(args, base, selection):
    from .academic_features import verify_cache

    binding = json.loads(args.academic_binding.read_bytes())
    plan = json.loads(args.academic_plan.read_bytes())
    provenance = binding["provenance"]
    if (
        sha256(args.academic_features) != binding["sidecar_sha256"]
        or provenance["plan_file_sha256"] != sha256(args.academic_plan)
        or provenance["selection_file_sha256"] != sha256(args.selection)
        or provenance["registration"] != plan["provenance"]
        or provenance["parent_sha256"] != selection["protocol"]["base_model_sha256"]
        or sha256(args.control_keys) != selection["band_controls_sha256"]
    ):
        raise ValueError("External academic numeric cache or cutoff control identity differs")
    members = plan["members"]
    ids, groups = {r["id"] for r in members}, {r["group"] for r in members}
    checks = {}

    def disjoint(name, other_ids, other_groups=()):
        shared_ids = len(ids.intersection(other_ids))
        shared_groups = len(groups.intersection(other_groups))
        checks[name] = {
            "document_collisions": shared_ids,
            "group_collisions": shared_groups if other_groups else None,
        }
        if shared_ids or shared_groups:
            raise ValueError("External academic membership overlaps " + name)

    ordinary = [r for rows in base.values() for r in rows]
    disjoint(
        "original_stack_calibration_and_development",
        {r.id for r in ordinary},
        {r.group for r in ordinary},
    )
    with sqlite3.connect(args.supplement.resolve().as_uri() + "?mode=ro", uri=True) as db:
        # Read identity fields alone from the signed cohort, including both clean parents.
        other = db.execute(
            "SELECT source_group,json_extract(payload,'$.human.id'),"
            "json_extract(payload,'$.machine.id'),json_extract(payload,'$.clean_human.id'),"
            "json_extract(payload,'$.clean_machine.id') FROM pairs"
        )
        supp_ids, supp_groups = set(), set()
        for raw, *keys in other:
            supp_ids.update(keys)
            supp_groups.add(fingerprint(raw))
        disjoint("all_supplemental_development_and_fitting_envelopes", supp_ids, supp_groups)
    with sqlite3.connect(args.control_keys.resolve().as_uri() + "?mode=ro", uri=True) as db:
        control = list(db.execute("SELECT id,grp FROM controls"))
        disjoint("independent_cutoff_controls", {r[0] for r in control}, {r[1] for r in control})
    for i, path in enumerate(args.encoder_fit_keys):
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            disjoint(
                f"encoder_training_envelope_{i}",
                {r[0] for r in db.execute("SELECT digest FROM vectors")},
            )
    result = defaultdict(list)
    with sqlite3.connect(args.academic_features.resolve().as_uri() + "?mode=ro", uri=True) as db:
        blob, complete, expected = db.execute(
            "SELECT provenance,complete,content_sha256 FROM meta"
        ).fetchone()
        _, digest, _ = verify_cache(db, members, complete=True)
        if (
            not complete
            or json.loads(blob) != provenance
            or digest != expected
            or digest != binding["content_sha256"]
        ):
            raise ValueError("External academic numeric content binding differs")
        for key, group, kind, generator, words, x, v in db.execute(
            "SELECT id,source,kind,generator,words,features,encoder FROM documents ORDER BY rowno"
        ):
            if (
                kind not in {"rewrite", "original_clean", "same_prompt_clean"}
                or generator == "human"
            ):
                raise ValueError("This published academic protocol has machine-origin inputs only")
            r = CachedRow(
                key,
                group,
                VALIDATION,
                1,
                words,
                (),
                np.frombuffer(x, dtype="<f8"),
                np.frombuffer(v, dtype="<f4"),
            )
            result["academic/" + kind].append(r)
            if kind == "rewrite":
                result["academic/rewrite_generator/" + generator].append(r)
            else:
                result["academic/clean_combined"].append(r)
    return result, {
        "registration": plan["provenance"],
        "numeric_content_sha256": binding["content_sha256"],
        "identity_checks": checks,
        "encoder_training_cache_sha256": [sha256(p) for p in args.encoder_fit_keys],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "parent",
        "incumbent",
        "probe",
        "features",
        "sidecar",
        "supplement",
        "selection",
        "original-selection",
        "cache",
        "out",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    for name in (
        "academic-plan",
        "academic-features",
        "academic-binding",
        "academic-out",
        "control-keys",
    ):
        p.add_argument("--" + name, type=Path)
    p.add_argument("--encoder-fit-keys", action="append", type=Path, default=[])
    args = p.parse_args(argv)
    auxiliary = (
        args.academic_plan,
        args.academic_features,
        args.academic_binding,
        args.academic_out,
        args.control_keys,
    )
    if any(auxiliary) and (not all(auxiliary) or len(args.encoder_fit_keys) != 2):
        p.error(
            "Academic diagnostics require the plan, features, binding, output, cutoff membership and both encoder fit key caches"
        )
    from vibechecker_engine.deep import DeepModel

    selection = json.loads(args.selection.read_bytes())
    protocol = selection["protocol"]
    if (
        sha256(args.incumbent) != selection["incumbent_sha256"]
        or sha256(args.parent) != protocol["base_model_sha256"]
        or sha256(args.supplement) != protocol["supplement_file_sha256"]
        or sha256(args.probe) != selection["probe_artifacts"]["mixture"]["artifact_sha256"]
    ):
        raise ValueError("Frozen artifact, probe or verified cohort identity mismatch")
    parent, model = (DeepModel.load(v) for v in (args.parent, args.incumbent))
    _, base, names, _, base_content = load_rows(
        args.features, parent, protocol["base_model_sha256"], False
    )
    if base_content != protocol["base_features_sha256"]:
        raise ValueError("Original numeric cache content differs from selection")
    orig = json.loads(args.original_selection.read_bytes())
    if (
        orig["lineage"] != model.refit_provenance
        or orig["selected_model_sha256"] != selection["incumbent_sha256"]
    ):
        raise ValueError("Original fit commitment does not bind the frozen incumbent")
    effective = effective_training(args.cache, base, orig)
    key = fingerprint("attack/paraphrase")
    academics = [
        r for part in (TRAIN, CALIBRATION, VALIDATION) for r in effective[part] if key in r.strata
    ]
    if (
        fingerprint(" ".join(sorted(r.id for r in base[VALIDATION])))
        != selection["primary_membership"]["scored_ids_sha256"]
    ):
        raise ValueError("Frozen development membership differs")
    probe = joblib.load(args.probe)
    groups = defaultdict(list)
    for r in academics:
        groups["primary/" + NAMES[r.role] + "/" + ORIGINS[r.label]].append(r)
    integer_roles = {"stack": TRAIN, "calibration": CALIBRATION, "stress": 3}
    supplemental_integrity = defaultdict(list)
    side_digest = hashlib.sha256()
    with sqlite3.connect(args.sidecar.resolve().as_uri() + "?mode=ro", uri=True) as db:
        for key, group, part, domain, label, words, x, v, refusal in db.execute(
            "SELECT * FROM docs ORDER BY id"
        ):
            side_digest.update(key.encode())
            if refusal is not None:
                side_digest.update(refusal.encode())
                continue
            side_digest.update(x)
            side_digest.update(v)
            groups[f"matched/{part}/{domain}/{ORIGINS[label]}"].append(
                CachedRow(
                    key,
                    group,
                    integer_roles[part],
                    label,
                    words,
                    (),
                    np.frombuffer(x, dtype="<f8"),
                    np.frombuffer(v, dtype="<f4"),
                )
            )
    if side_digest.hexdigest() != selection["sidecar"]["content_sha256"]:
        raise ValueError("Matched numeric content differs from completed comparison")
    for part in integer_roles:
        for pair in load_rewrite_pairs(args.supplement, role=part):
            for label, (rewrite, original) in enumerate(
                ((pair.human, pair.clean_human), (pair.machine, pair.clean_machine))
            ):
                group = f"matched/{part}/{pair.domain}/{ORIGINS[label]}"
                retained = {r.id: r for r in groups[group]}
                if rewrite.id not in retained:
                    continue

                def native(d, group=pair.source_group):
                    return {
                        "id": d.publisher_id,
                        "source_id": group,
                        "adv_source_id": d.parent_id,
                        "model": d.generator,
                        "generation": d.text,
                    }

                supplemental_integrity[group].append(
                    (
                        retained[rewrite.id],
                        native(rewrite),
                        native(original),
                        native(pair.clean_human),
                    )
                )
    academic, academic_provenance = (
        academic_groups(args, base, selection) if all(auxiliary) else ({}, {})
    )
    scored_groups = {**groups, **academic}
    with threadpool_limits(limits=1):
        score_stages = {
            k: stages(model.stacker, model.probe, rows) for k, rows in sorted(scored_groups.items())
        }
        mixture = {
            k: distribution(probe.predict_proba(np.stack([r.encoder for r in rows]))[:, 1])
            for k, rows in sorted(groups.items())
        }
    for name in ("genre/essay", "fairness/ESL-essay", "dataset/liang/toefl", "writer/native_proxy"):
        names.setdefault(fingerprint(name), name)
    with threadpool_limits(limits=1):
        replay, curves = challenger_ranges(
            effective,
            groups,
            scored_groups,
            {"ordinary-control": model.probe, "mixture": probe},
            selection,
            names,
        )
    report = {
        "scheme": "frozen-development-origin-diagnostics-v1",
        "model": selection["incumbent_sha256"],
        "v3_selection_sha256": sha256(args.selection),
        "scope": "Original cached training, calibration, live development validation; authenticated books/news matched stack, calibration and development stress only.",
        "similarity_rule": "Casefold and split on whitespace. Near means word sequence match ratio >= .90 or contiguous five-token set Jaccard >= .80.",
        "primary_integrity": native_academic(academics, args.cache),
        "matched_integrity": {k: integrity(v) for k, v in sorted(supplemental_integrity.items())},
        "incumbent_scoring_stages": {k: score_stages[k] for k in groups},
        "fixed_origin_probe": mixture,
        "length_calibration_curves": {"incumbent": curve_support(model.stacker), **curves},
        "replayed_challenger_scoring_stages": {
            model: {k: stats[k] for k in groups} for model, stats in replay.items()
        },
    }
    write_json(report, args.out)
    if academic:
        write_json(
            {
                "scheme": "registered-academic-development-frozen-model-diagnostics-v1",
                "v3_selection_sha256": sha256(args.selection),
                "incumbent_sha256": selection["incumbent_sha256"],
                "scope": "Previously frozen v2 incumbent and four recorded v3 development challengers. All academic inputs are machine-origin.",
                "provenance": academic_provenance,
                "publisher_integrity": native_academic(academic["academic/rewrite"], args.cache),
                "incumbent": {k: score_stages[k] for k in academic},
                "v3_candidates": {
                    model: {k: stats[k] for k in academic} for model, stats in replay.items()
                },
            },
            args.academic_out,
        )


if __name__ == "__main__":
    main()
