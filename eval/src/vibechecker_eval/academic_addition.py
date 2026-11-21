"""Reproduce two anchored Deep refits with verified, source-matched academic additions."""

import argparse
import hashlib
import json
import os
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .academic_features import extract_numeric, verify_cache
from .academic_intake import ARTIFACTS, HUMAN_DEV, project, study_paths
from .band_controls import calibrate_high_band, load_band_controls
from .deep_runner import write_json
from .loaders import fingerprint
from .metrics import rate
from .refit import CachedRow, _copy_model, append_probe, load_rows, validation_quality
from .refit_cache import CALIBRATION, TRAIN, VALIDATION, runtime_identity, same_numeric_runtime
from .registry import sha256
from .rewrite_diagnostics import academic_groups, effective_training, stages
from .rewrite_refit import admissibility, displayed, sensitivity, stress_metrics
from .rewrite_sidecar import finite, metadata_hash

STRESS = 3
SELECTION_RULE = "Require all original v3 admissibility checks, preserve at least 90% of v2 high hits independently on 66 machine rewrites and 54 exact clean machine parents, and incur no additional high false positives on the disjoint native human development cohort. Rank admissible anchors by primary worst-stratum ECE, primary pooled ECE, matched stress Brier, then anchor."
ROLES = {"stack": TRAIN, "calibration": CALIBRATION, "stress": STRESS}


def member_metadata(rows):
    return [{k: v for k, v in r.items() if k != "text"} for r in rows]


def freeze(paths, study_sha):
    parent_json = json.loads(paths["v3_selection"].read_bytes())
    previous = parent_json["protocol"]["supplement"]
    original = json.loads(paths["machine_manifest"].read_bytes())
    for native, expected in (
        ("historical_sha256", "historical_envelope_sha256"),
        ("prospective_sha256", "prospective_reservation_sha256"),
        ("prior_stack_sha256", "prior_refit_plan_sha256"),
    ):
        if original[native] != previous[expected]:
            raise ValueError(
                "Academic source isolation used a different protected cohort commitment"
            )
    rows, summary = project(paths)
    return rows, {
        "scheme": "academic-origin-two-anchor-study-v1",
        "study_sha256": study_sha,
        "training": summary,
        "members": member_metadata(rows),
        "selection_sha256": summary["selection_sha256"],
        "v3_selection_sha256": sha256(paths["v3_selection"]),
        "incumbent_sha256": parent_json["incumbent_sha256"],
        "settings": {
            "anchors": [0.5, 0.75],
            "max_leaf_nodes": 7,
            "l2_regularization": 1.0,
            "seed": 42,
            "probe_sha256": parent_json["probe_artifacts"]["mixture"]["artifact_sha256"],
            "bootstrap_curves": 200,
            "reference_prior": 0.5,
        },
        "ready": summary["ready"],
        "selection_rule": SELECTION_RULE,
    }


def check_models(paths, v3):
    from vibechecker_engine.deep import DeepModel

    if (
        sha256(paths["v1_parent"]) != v3["protocol"]["base_model_sha256"]
        or sha256(paths["v2_incumbent"]) != v3["incumbent_sha256"]
        or sha256(paths["probe"]) != v3["probe_artifacts"]["mixture"]["artifact_sha256"]
        or sha256(paths["band_controls"]) != v3["band_controls_sha256"]
        or sha256(paths["rewrite_supplement"]) != v3["protocol"]["supplement_file_sha256"]
    ):
        raise ValueError(
            "Academic refit requires the exact frozen v1 heads, v2 incumbent, v3 probe and source controls"
        )
    parent, incumbent = DeepModel.load(paths["v1_parent"]), DeepModel.load(paths["v2_incumbent"])
    probe = joblib.load(paths["probe"])
    if (
        joblib.hash(parent.heads) != joblib.hash(incumbent.heads)
        or parent.identity != incumbent.identity
        or probe.training_provenance_ != v3["probe_artifacts"]["mixture"]["training_provenance"]
        or parent.training_scope != incumbent.training_scope
        or parent.training_scope["commercial_only"]
    ):
        raise ValueError(
            "Source weights, research license or supervised probe qualification differs"
        )
    return parent, incumbent, probe


def read_rewrite_rows(path, v3):
    result = defaultdict(list)
    groups = {}
    digest = hashlib.sha256()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        value, complete = db.execute("SELECT provenance,complete FROM meta").fetchone()
        record = json.loads(value)
        if (
            not complete
            or {k: v for k, v in record.items() if k != "runtime"} != v3["protocol"]
            or record["runtime"] != v3["sidecar"]["runtime"]
        ):
            raise ValueError("Original rewrite sidecar selection or runtime differs")
        for key, g, part, domain, label, words, x, v, refusal in db.execute(
            "SELECT * FROM docs ORDER BY id"
        ):
            digest.update(key.encode())
            if refusal:
                digest.update(refusal.encode())
                continue
            digest.update(x)
            digest.update(v)
            features = finite(np.frombuffer(x, dtype="<f8"), 13, "<f8")
            vector = finite(np.frombuffer(v, dtype="<f4"), 769, "<f4")
            result[ROLES[part]].append(
                CachedRow(key, g, ROLES[part], label, words, (), features, vector)
            )
            groups[g] = domain
    if digest.hexdigest() != v3["sidecar"]["content_sha256"]:
        raise ValueError("Original rewrite sidecar numeric digest differs")
    for role, items in result.items():
        by_group = defaultdict(list)
        for r in items:
            by_group[r.group].append(r)
        result[role] = sorted(
            (
                r
                for pair in by_group.values()
                if len(pair) == 2 and {v.label for v in pair} == {0, 1}
                for r in pair
            ),
            key=lambda r: (groups[r.group], r.group, r.id),
        )
    return result, groups


def read_academic(path, receipt, plan):
    members = plan["members"]
    if (
        receipt["sidecar_sha256"] != sha256(path)
        or receipt["provenance"]["selection_sha256"] != plan["selection_sha256"]
    ):
        raise ValueError("Academic sidecar binding differs")
    parts = defaultdict(list)
    subjects = defaultdict(list)
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        blob, complete, expected = db.execute(
            "SELECT provenance,complete,content_sha256 FROM meta"
        ).fetchone()
        _, digest, _ = verify_cache(db, members, complete=True)
        if (
            not complete
            or json.loads(blob) != receipt["provenance"]
            or digest != expected
            or digest != receipt["content_sha256"]
        ):
            raise ValueError("Academic numeric sidecar does not match its completion binding")
        for idx, key, g, _, _, _, words, x, v in db.execute(
            "SELECT * FROM documents ORDER BY rowno"
        ):
            m = members[idx]
            part = VALIDATION if m["role"] == HUMAN_DEV else ROLES[m["role"]]
            row = CachedRow(
                key,
                g,
                part,
                m["label"],
                words,
                (),
                np.frombuffer(x, dtype="<f8"),
                np.frombuffer(v, dtype="<f4"),
            )
            if words != m["words"]:
                raise ValueError("Frozen research and production word counts differ")
            parts[part].append(row)
            if m["role"] == HUMAN_DEV:
                subjects["pooled"].append(row)
                subjects[f"source/{m['source']}"].append(row)
                subjects[f"subject/{m['subject'] or 'unknown'}"].append(row)
    return parts, subjects


def matrix(rows, probe):
    return append_probe(
        np.stack([r.features for r in rows]), np.stack([r.encoder for r in rows]), probe
    )


def human_checks(stacker, probe, groups):
    summary = {}
    for name, rows in groups.items():
        logits = displayed(stacker, matrix(rows, probe), rows)
        summary[name] = {
            "documents": len(rows),
            "high_false_positive": rate(int(sum(logits >= stacker.high_threshold)), len(rows)),
            "mixed_or_higher_false_positive": rate(
                int(sum(logits >= stacker.low_threshold)), len(rows)
            ),
            "displayed_mean": float(np.mean(logits) / 100),
            "brier": float(np.mean((logits / 100) ** 2)),
        }
    return summary


def machine_checks(stacker, probe, groups):
    result = {}
    for key, rows in groups.items():
        diag = stages(stacker, probe, rows)
        diag["high_detection"] = rate(diag["high_band"]["hits"], len(rows))
        result[key] = diag
    return result


def academic_admissibility(machines, humans, baseline_machines, baseline_humans):
    reasons = []
    for key, count in (("academic/rewrite", 66), ("academic/original_clean", 54)):
        candidate = machines[key]["high_detection"]
        base = baseline_machines[key]["high_detection"]
        if candidate["denominator"] != count or base["denominator"] != count or not base["count"]:
            raise ValueError(
                "Independent academic machine registration or incumbent detections differ"
            )
        if 10 * candidate["count"] < 9 * base["count"]:
            reasons.append(f"retained fewer than 90% of v2 high detections in {key}")
    new = humans["pooled"]["high_false_positive"]
    old = baseline_humans["pooled"]["high_false_positive"]
    if not new["denominator"] or new["denominator"] != old["denominator"]:
        raise ValueError("Expected the same independent native-human academic papers")
    if new["count"] > old["count"]:
        reasons.append(
            "more high-band false positives on independent native academic papers than v2"
        )
    return reasons


def select_winner(candidates):
    eligible = [name for name, report in candidates.items() if not report["admission_reasons"]]
    if not eligible:
        return "incumbent"

    def rank(name):
        item = candidates[name]
        return (
            item["ordinary"]["worst_stratum_ece"],
            item["ordinary"]["pooled_ece"],
            item["books_news_stress"]["strata"]["pooled"]["brier"],
            item["anchor"],
        )

    return min(eligible, key=rank)


def compare(args, paths, plan, v3, parent, incumbent, probe):
    from vibechecker_engine.deep import DeepModel, ProbeDeepStacker

    info, raw, names, _, content = load_rows(
        paths["base_features"], parent, sha256(paths["v1_parent"]), False
    )
    if content != v3["protocol"]["base_features_sha256"]:
        raise ValueError("Original numeric Deep cache differs")
    v2 = json.loads(paths["v2_selection"].read_bytes())
    if (
        v2["lineage"] != incumbent.refit_provenance
        or v2["selected_model_sha256"] != v3["incumbent_sha256"]
    ):
        raise ValueError("V2 lineage or model differs")
    base = effective_training(args.cache, raw, v2)
    for name in ("genre/essay", "fairness/ESL-essay", "dataset/liang/toefl", "writer/native_proxy"):
        names.setdefault(fingerprint(name), name)
    extra, domains = read_rewrite_rows(paths["rewrite_sidecar"], v3)
    receipt = json.loads(args.binding.read_bytes())
    if (
        sha256(args.binding) != args.binding_sha256
        or receipt["provenance"]["study_sha256"] != args.study_sha256
        or receipt["provenance"]["plan_sha256"] != sha256(args.plan)
        or receipt["provenance"]["runtime"] != v3["sidecar"]["runtime"]
    ):
        raise ValueError("Academic input receipt or runtime differs from frozen plan")
    additions, human = read_academic(args.sidecar, receipt, plan)
    guard = [r for part in (*base.values(), *extra.values(), *additions.values()) for r in part]
    controls = load_band_controls(
        paths["band_controls"],
        expected_sha256=v3["band_controls_sha256"],
        parent=incumbent,
        parent_sha256=v3["incumbent_sha256"],
        expected_runtime=info["runtime"],
        excluded_ids={r.id for r in guard},
        excluded_groups={r.group for r in guard},
    )
    if controls.provenance["runtime"] != receipt["provenance"]["runtime"]:
        raise ValueError("Independent high-cutoff evidence used another extractor")
    auxiliary, aux_provenance = academic_groups(
        SimpleNamespace(
            academic_binding=paths["academic_binding"],
            academic_plan=paths["academic_plan"],
            academic_features=paths["academic_features"],
            selection=paths["v3_selection"],
            supplement=paths["rewrite_supplement"],
            control_keys=paths["band_controls"],
            encoder_fit_keys=[paths["encoder_original"], paths["encoder_expanded"]],
        ),
        raw,
        v3,
    )
    baseline = v3["incumbent"]
    old_x = matrix(base[VALIDATION], incumbent.probe)
    old_q = validation_quality(incumbent.stacker, old_x, base[VALIDATION], names)
    old_s = stress_metrics(
        displayed(incumbent.stacker, matrix(extra[STRESS], incumbent.probe), extra[STRESS]),
        extra[STRESS],
        domains,
    )
    if old_q != baseline["ordinary"] or old_s != baseline["stress"]:
        raise ValueError("Original v2 primary or stress observations no longer reproduce")
    fit_rows = {p: [*base[p], *extra[p], *additions[p]] for p in (TRAIN, CALIBRATION)}
    x = {p: matrix(rows, probe) for p, rows in fit_rows.items()}
    y = {p: np.asarray([r.label for r in rows]) for p, rows in fit_rows.items()}
    val = base[VALIDATION]
    val_x = matrix(val, probe)
    val_y = [r.label for r in val]
    stress = extra[STRESS]
    stress_x = matrix(stress, probe)
    scope = {
        "scheme": "source-matched-academic-origin-addition-v1",
        "commercial_only": False,
        "role_support": plan["training"],
        "study_sha256": args.study_sha256,
        "numeric_content_sha256": receipt["content_sha256"],
    }
    supplements = [*v3["candidate_training_supplements"], scope]
    baseline_machine = machine_checks(incumbent.stacker, incumbent.probe, auxiliary)
    baseline_human = human_checks(incumbent.stacker, incumbent.probe, human)
    candidates = {}
    args.candidate_dir.mkdir(parents=True, exist_ok=True)
    for anchor in (0.5, 0.75):
        tag = f"academic-anchor{anchor:g}"
        stacker = ProbeDeepStacker.fit(
            x[TRAIN],
            y[TRAIN],
            x[CALIBRATION],
            y[CALIBRATION],
            [r.words for r in fit_rows[CALIBRATION]],
            seed=42,
            max_leaf_nodes=7,
            l2_regularization=1.0,
            probe_anchor=anchor,
        )
        previous = stacker.high_threshold
        try:
            cutoff = calibrate_high_band(stacker, probe, controls)
        except ValueError as exc:
            candidates[tag] = {"admission_reasons": [str(exc)], "cutoff_supported": False}
            continue
        scores = displayed(stacker, val_x, val)
        before = sensitivity(scores, val_y, previous)
        after = sensitivity(scores, val_y, stacker.high_threshold)
        primary = validation_quality(stacker, val_x, val, names)
        stress_q = stress_metrics(displayed(stacker, stress_x, stress), stress, domains)
        reasons = admissibility(primary, stress_q, before, after, baseline)
        academic_machine = machine_checks(stacker, probe, auxiliary)
        academic_human = human_checks(stacker, probe, human)
        reasons.extend(
            academic_admissibility(
                academic_machine, academic_human, baseline_machine, baseline_human
            )
        )
        model = DeepModel(parent.heads, stacker, parent.identity, probe=probe)
        model.training_scope = {**parent.training_scope, "supplements": supplements}
        model.fit_selection = {
            **incumbent.fit_selection,
            "academic_selection_sha256": plan["selection_sha256"],
            "rewrite_sidecar_selection_sha256": v3["protocol"]["selection_sha256"],
        }
        model.fit_counts = {
            **incumbent.fit_counts,
            "stacker": dict(Counter(map(int, y[TRAIN]))),
            "calibration": dict(Counter(map(int, y[CALIBRATION]))),
            "academic_role_support": plan["training"]["accepted"],
        }
        model.refit_provenance = {
            **incumbent.refit_provenance,
            "candidate": tag,
            "probe_sha256": sha256(paths["probe"]),
            "academic_study_sha256": args.study_sha256,
            "academic_sidecar_content_sha256": receipt["content_sha256"],
            "supplements_sha256": metadata_hash(supplements),
            "band_controls_sha256": v3["band_controls_sha256"],
            "band_control": cutoff,
        }
        artifact = args.candidate_dir / (tag + ".joblib")
        if artifact.exists():
            prior = DeepModel.load(artifact)
            if prior.refit_provenance != model.refit_provenance or joblib.hash(
                prior.stacker
            ) != joblib.hash(stacker):
                raise ValueError("Existing candidate differs; supply an unused output directory")
        else:
            model.save(artifact)
        old = v3["candidates"][f"mixture-anchor{anchor:g}"]
        old_primary, old_stress = old["ordinary"], old["stress"]["strata"]["pooled"]
        current_stress = stress_q["strata"]["pooled"]
        candidates[tag] = {
            "artifact_sha256": sha256(artifact),
            "anchor": anchor,
            "ordinary": primary,
            "books_news_stress": stress_q,
            "original_same_anchor_control": {
                "thresholds": old_primary["thresholds"],
                "pooled_ece": old_primary["pooled_ece"],
                "worst_stratum_ece": old_primary["worst_stratum_ece"],
                "pooled_ece_change": primary["pooled_ece"] - old_primary["pooled_ece"],
                "worst_ece_change": primary["worst_stratum_ece"] - old_primary["worst_stratum_ece"],
                "stress_change": {
                    k: current_stress[k] - old_stress[k]
                    for k in ("brier", "log_loss", "pair_concordance", "auroc")
                },
            },
            "admission_reasons": reasons,
            "high_before": before,
            "high_after": after,
            "band_control": cutoff,
            "academic_human_development": academic_human,
            "independent_academic_machine": academic_machine,
        }
    winner = select_winner(candidates)
    selected = (
        paths["v2_incumbent"]
        if winner == "incumbent"
        else args.candidate_dir / (winner + ".joblib")
    )
    if args.model_out.exists() and sha256(args.model_out) != sha256(selected):
        raise ValueError("Selected model destination already contains a different artifact")
    _copy_model(selected, args.model_out)
    write_json(
        {
            "scheme": "academic-origin-additive-comparison-v1",
            "study_sha256": args.study_sha256,
            "plan_sha256": sha256(args.plan),
            "numeric_content_sha256": receipt["content_sha256"],
            "support": plan["training"],
            "settings": plan["settings"],
            "selected": winner,
            "selected_model_sha256": sha256(args.model_out),
            "selection_rule": SELECTION_RULE,
            "selection_reason": "All proposed anchors were rejected"
            if winner == "incumbent"
            else "First admissible anchor by the frozen ranking",
            "v2_incumbent_sha256": v3["incumbent_sha256"],
            "v3_control_report_sha256": sha256(paths["v3_selection"]),
            "incumbent_academic_human_development": baseline_human,
            "incumbent_independent_academic_machine": baseline_machine,
            "academic_machine_development": aux_provenance["registration"],
            "candidates": candidates,
        },
        args.out,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    cmds = parser.add_subparsers(dest="command", required=True)
    binder = cmds.add_parser(
        "bind", help="Hash a portable artifact layout before freezing an outcome-blind study plan"
    )
    for key in ("layout", "root", "study"):
        binder.add_argument("--" + key, type=Path, required=True)
    for action in ("plan", "collect", "compare"):
        p = cmds.add_parser(action)
        for key in ("study", "plan"):
            p.add_argument("--" + key, type=Path, required=True)
        p.add_argument("--study-sha256", required=True)
        if action == "plan":
            p.add_argument("--receipt", type=Path)
        if action != "plan":
            p.add_argument("--plan-sha256", required=True)
            p.add_argument("--sidecar", type=Path, required=True)
            p.add_argument("--binding", type=Path, required=True)
        if action == "compare":
            p.add_argument("--binding-sha256", required=True)
            p.add_argument("--model-out", type=Path, required=True)
            p.add_argument("--candidate-dir", type=Path, required=True)
            p.add_argument("--cache", type=Path, required=True)
            p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "bind":
        layout = json.loads(args.layout.read_bytes())
        if set(layout) != ARTIFACTS:
            parser.error(
                "The artifact layout must specify every registered source, model and numeric cache"
            )
        files = {}
        for name, location in sorted(layout.items()):
            target = (args.root / location).resolve()
            files[name] = {
                "path": os.path.relpath(target, args.study.resolve().parent),
                "sha256": sha256(target),
            }
        write_json({"scheme": "academic-origin-additive-v1", "files": files}, args.study)
        print(sha256(args.study))
        return
    paths = study_paths(args.study, args.study_sha256)
    user_paths = [
        getattr(args, k).resolve()
        for k in ("study", "plan", "sidecar", "binding", "out", "model_out", "receipt")
        if getattr(args, k, None) is not None
    ]
    if len(set(user_paths)) != len(user_paths) or set(user_paths) & set(paths.values()):
        raise ValueError("Study files and their new outputs must use separate paths")
    rows, plan = freeze(paths, args.study_sha256)
    if args.command == "plan":
        if args.plan.exists() and json.loads(args.plan.read_bytes()) != plan:
            raise ValueError("An existing plan binds another academic study")
        write_json(plan, args.plan)
        if args.receipt:
            write_json(
                {
                    **{k: v for k, v in plan.items() if k != "members"},
                    "plan_file_sha256": sha256(args.plan),
                    "file_sha256": {k: sha256(path) for k, path in paths.items()},
                    "numeric_features_extracted": False,
                    "candidate_predictions_computed": False,
                },
                args.receipt,
            )
        return
    if (
        sha256(args.plan) != args.plan_sha256
        or json.loads(args.plan.read_bytes()) != plan
        or not plan["ready"]
    ):
        raise ValueError("Study is not ready or frozen membership differs")
    v3 = json.loads(paths["v3_selection"].read_bytes())
    parent, incumbent, probe = check_models(paths, v3)
    if args.command == "collect":
        runtime = runtime_identity()
        if (
            not same_numeric_runtime(v3["protocol"]["base_runtime"], runtime)
            or runtime != v3["sidecar"]["runtime"]
        ):
            raise ValueError("Academic collector requires the bound rewrite-study runtime")
        provenance = {
            "scheme": "source-matched-academic-numeric-v1",
            "study_sha256": args.study_sha256,
            "plan_sha256": args.plan_sha256,
            "selection_sha256": plan["selection_sha256"],
            "source_order_sha256": plan["training"]["source_order_sha256"],
            "runtime": runtime,
            "backend": v3["protocol"]["backend"],
            "quick_prefill": v3["protocol"]["quick_prefill"],
            "feature_names": v3["protocol"]["feature_names"],
            "encoder_vector": v3["protocol"]["encoder_vector"],
            "parent_sha256": v3["protocol"]["base_model_sha256"],
            "heads": joblib.hash(parent.heads),
            "weights": parent.identity,
        }
        write_json(
            extract_numeric(args.sidecar, rows, parent, v3["protocol"], provenance), args.binding
        )
    else:
        with threadpool_limits(limits=1):
            compare(args, paths, plan, v3, parent, incumbent, probe)


if __name__ == "__main__":
    main()
