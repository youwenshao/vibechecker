"""Refit the document model with frozen heads; choose on validation and keep final test untouched."""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .deep_runner import write_json
from .loaders import examples, fingerprint
from .metrics import Observation, gates, metrics
from .refit_cache import CALIBRATION, TRAIN, VALIDATION, digest_strings
from .registry import registry, select, sha256
from .source_groups import human_source_aliases


@dataclass(frozen=True)
class CachedRow:
    id: str
    group: str
    role: int
    label: int
    words: int
    strata: tuple[str, ...]
    features: np.ndarray
    encoder: np.ndarray | None


def load_rows(path, source, parent_sha, commercial_only):
    from vibechecker_engine.deep import DEEP_FEATURE_NAMES
    from vibechecker_engine.signals import ENCODER_VECTOR_VERSION

    uri = path.resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    try:
        db.execute("BEGIN")
        meta = dict(db.execute("SELECT key,value FROM meta"))
        if meta.get("complete") != "1":
            raise ValueError("Incomplete feature cache; resume deep-cache before fitting")
        info = json.loads(meta["provenance"])
        if (
            info.get("schema") != 1
            or info.get("frozen_parent_sha256") != parent_sha
            or info.get("training_scope") != getattr(source, "training_scope", None)
            or info["training_scope"]["weights"] != source.identity
            or info["training_scope"]["commercial_only"] != commercial_only
            or tuple(info["feature_names"]) != DEEP_FEATURE_NAMES
            or info.get("encoder_vector") not in (None, ENCODER_VECTOR_VERSION)
        ):
            raise ValueError(
                "Feature cache does not match the frozen artifact, feature schema or licensing scope"
            )
        result = defaultdict(list)
        groups = {}
        plan_rows = []
        refusals = Counter()
        content = hashlib.sha256()
        for key, group, part, label, words, strata_json, values, vector, refusal in db.execute(
            "SELECT id, group_id, role, label, words, strata, features, encoder, refusal FROM documents ORDER BY id"
        ):
            if (
                part not in (TRAIN, CALIBRATION, VALIDATION)
                or groups.setdefault(group, part) != part
                or label not in (0, 1)
                or not 300 <= words <= 2500
            ):
                raise ValueError("Invalid or overlapping source groups in cached partitions")
            plan_rows.append(f"{key} {group} {part} {label} {words}")
            content.update(key.encode() + strata_json.encode())
            if refusal is not None:
                refusals[part] += 1
                content.update(str(refusal).encode())
                continue
            x = np.frombuffer(values, dtype="<f8")
            encoder = np.frombuffer(vector, dtype="<f4") if vector is not None else None
            if (
                x.shape != (len(DEEP_FEATURE_NAMES),)
                or not np.isfinite(x).all()
                or (info["encoder_vector"] is None) != (encoder is None)
                or (
                    encoder is not None
                    and (encoder.shape != (769,) or not np.isfinite(encoder).all())
                )
            ):
                raise ValueError("Invalid numeric feature cache")
            content.update(values)
            if vector:
                content.update(vector)
            result[part].append(
                CachedRow(
                    key, group, part, label, words, tuple(json.loads(strata_json)), x, encoder
                )
            )
        if (
            len(plan_rows) != info["selected"]
            or digest_strings(plan_rows) != info["selection_sha256"]
        ):
            raise ValueError("Feature cache no longer contains its exact selected cohort")
        if any(
            {r.label for r in result[part]} != {0, 1} for part in (TRAIN, CALIBRATION, VALIDATION)
        ):
            raise ValueError("Both labels are required in each usable partition")
        return (
            info,
            result,
            json.loads(meta.get("strata", "{}")),
            dict(refusals),
            content.hexdigest(),
        )
    finally:
        db.close()


def eligible_fit_rows(info, rows, cache, registry_path=None):
    scope = info["training_scope"]
    datasets = select(registry(registry_path), scope["dataset_order"], scope["commercial_only"])
    manifest = {
        d.id: {"version": d.version, "sha256": [a.sha256 for a in d.artifacts]} for d in datasets
    }
    if manifest != scope["manifest"] or list(manifest) != scope["dataset_order"]:
        raise ValueError(
            "Source alias scan requires the original pinned dataset manifest and order"
        )
    # The loader verifies each artifact's SHA before reading its examples. Short
    # passages and eval-only shards can link generated variants from distinct groups.
    aliases = human_source_aliases(examples(datasets, cache))
    ambiguous = {fingerprint(raw) for raw in aliases.groups}
    effective = {}
    excluded = {}
    kept = {}

    def selection(items):
        groups = sorted({r.group for r in items})
        return {
            "documents": len(items),
            "groups": len(groups),
            "document_ids_sha256": digest_strings(sorted(r.id for r in items)),
            "group_ids_sha256": digest_strings(groups),
        }

    for part, name in ((TRAIN, "train"), (CALIBRATION, "calibration"), (VALIDATION, "validation")):
        items = rows[part]
        matching = [r for r in items if r.group in ambiguous]
        if part == VALIDATION:
            effective[part] = items
            retained = selection(matching)
        else:
            effective[part] = [r for r in items if r.group not in ambiguous]
            excluded[name] = selection(matching)
            if {r.label for r in effective[part]} != {0, 1}:
                raise ValueError(
                    f"Both labels are required in {name} after source alias quarantine"
                )
        kept[name] = selection(effective[part])
    summary = {
        "source_aliases": aliases.summary(),
        "excluded": excluded,
        "effective": kept,
        "validation_aliases_retained": retained,
        "effective_selection_sha256": digest_strings(
            sorted(
                f"{r.id} {r.group} {r.role} {r.label} {r.words}"
                for part in effective.values()
                for r in part
            )
        ),
    }
    return effective, summary


def validate_probe(probe, info, source_aliases):
    from vibechecker_engine.signals import ENCODER_VECTOR_VERSION

    p = getattr(probe, "training_provenance_", None)
    backend = info.get("backend")
    if (
        not isinstance(p, dict)
        or not isinstance(backend, str)
        or not backend.strip()
        or p.get("backend") != backend
    ):
        raise ValueError("Probe and feature cache must identify the same training backend")
    scope = info["training_scope"]
    encoder_digest = scope["weights"]["ENCODER"].get("model.safetensors")
    valid_hash = re.compile(r"[0-9a-f]{64}").fullmatch
    if (
        not encoder_digest
        or info["encoder_vector"] != ENCODER_VECTOR_VERSION
        or p.get("encoder_sha256") != encoder_digest
        or p.get("encoder_files") != scope["weights"]["ENCODER"]
        or p.get("quick_prefill") != info["quick_prefill"]
        or p.get("manifest") != scope["manifest"]
        or p.get("source_aliases") != source_aliases
        or p.get("commercial_only") is not scope["commercial_only"]
        or p.get("partition") != "train"
        or p.get("head_fold") != 0
        or p.get("vector_version") != ENCODER_VECTOR_VERSION
        or not isinstance(p.get("seed"), int)
        or not isinstance(p.get("fit_counts"), dict)
        or not valid_hash(str(p.get("fit_group_ids_sha256")))
        or not valid_hash(str(p.get("fit_document_ids_sha256")))
        or not np.array_equal(getattr(probe, "classes_", []), [0, 1])
        or getattr(probe, "n_features_in_", None) != 769
    ):
        raise ValueError(
            "Probe must use the pinned encoder, licensed manifest, source alias quarantine and disjoint training head fold"
        )
    return p


def append_probe(features, encoder_vectors, probe):
    posterior = np.asarray(probe.predict_proba(encoder_vectors), dtype=float)
    if (
        posterior.shape != (len(features), 2)
        or not np.isfinite(posterior).all()
        or np.any((posterior < 0) | (posterior > 1))
    ):
        raise ValueError("Invalid frozen probe probabilities")
    return np.column_stack((features, posterior[:, 1]))


def validation_quality(stacker, matrix, rows, names):
    from vibechecker_engine.stacker import length_bin

    with threadpool_limits(limits=1, user_api="openmp"):
        raw = stacker.classifier.predict_proba(matrix)[:, 1]
    groups = defaultdict(list)
    observations = []
    for value, r in zip(raw, rows, strict=True):
        curve = stacker.calibrators.get(length_bin(r.words), stacker.calibrators["pooled"])
        score = int(np.rint(100 * curve.point(value))) / 100
        row = Observation(r.id, r.label, score, "", "test", "", "", "", "", r.words, None)
        observations.append(row)
        for stratum in r.strata:
            groups[names.get(stratum, stratum)].append(row)
    mixed, high = stacker.low_threshold / 100, stacker.high_threshold / 100
    summary = {
        "pooled": metrics(observations, mixed, high),
        **{k: metrics(group, mixed, high) for k, group in sorted(groups.items())},
    }
    worst = max(groups, key=lambda k: summary[k]["ece"])
    checks = gates(summary, quick=False, deep=True)
    return {
        "scored_ids_sha256": fingerprint(" ".join(sorted(r.id for r in observations))),
        "pooled_ece": summary["pooled"]["ece"],
        "worst_stratum_ece": summary[worst]["ece"],
        "worst_stratum": worst,
        "gates": checks,
        "metrics": summary,
        "thresholds": {"mixed": mixed, "high": high},
    }


def _copy_model(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
        temp = Path(tmp.name)
    try:
        shutil.copyfile(source, temp)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def run_refit(args):
    from vibechecker_engine.deep import DeepModel, DeepStacker, ProbeDeepStacker

    probe_paths = [args.probe] if isinstance(args.probe, Path) else (args.probe or [])
    probe_paths = list(dict.fromkeys(p.resolve() for p in probe_paths))
    paths = [args.model_in, args.features, args.model_out, args.selection_out, *probe_paths]
    if len({p.resolve() for p in paths}) != len(paths):
        raise ValueError("Refit inputs, output model and validation report must use distinct paths")
    source = DeepModel.load(args.model_in)
    parent_sha = sha256(args.model_in)
    info, rows, names, refused, content_sha = load_rows(
        args.features, source, parent_sha, args.commercial_only
    )
    rows, quarantine = eligible_fit_rows(info, rows, args.cache, getattr(args, "registry", None))
    source_aliases = quarantine["source_aliases"]
    # Existing caches may predate the human-readable aggregate stratum dictionary.
    for name in ("genre/essay", "fairness/ESL-essay", "dataset/liang/toefl", "writer/native_proxy"):
        names.setdefault(fingerprint(name), name)
    probes, probe_reports = {}, {}
    for path in probe_paths:
        digest = sha256(path)
        if digest not in probes:
            probe = joblib.load(path)
            details = validate_probe(probe, info, source_aliases)
            probes[digest] = probe
            probe_reports[digest] = {
                "artifact_names": [],
                "training_provenance": details,
                "candidates": [],
            }
        if path.name not in probe_reports[digest]["artifact_names"]:
            probe_reports[digest]["artifact_names"].append(path.name)
    plain = {part: np.vstack([row.features for row in items]) for part, items in rows.items()}
    parent_probe = getattr(source, "probe", None)
    if parent_probe is not None:
        validate_probe(parent_probe, info, source_aliases)
    encoder_vectors = {}
    if probes or parent_probe is not None:
        for part, items in rows.items():
            if any(row.encoder is None for row in items):
                raise ValueError("Probe candidates require cached encoder vectors")
            encoder_vectors[part] = np.vstack([row.encoder for row in items])
    inputs = {
        digest: {
            part: append_probe(features, encoder_vectors[part], probe)
            for part, features in plain.items()
        }
        for digest, probe in probes.items()
    }
    parent_validation = plain[VALIDATION]
    if parent_probe is not None:
        parent_digest = (getattr(source, "refit_provenance", None) or {}).get("probe_sha256")
        parent_validation = (
            inputs[parent_digest][VALIDATION]
            if parent_digest in inputs
            else append_probe(parent_validation, encoder_vectors[VALIDATION], parent_probe)
        )
    validation = rows[VALIDATION]
    expected_ids = fingerprint(" ".join(sorted(row.id for row in validation)))

    def measure(stacker, matrix):
        q = validation_quality(stacker, matrix, validation, names)
        if q["scored_ids_sha256"] != expected_ids or q["metrics"]["pooled"]["count"] != len(
            validation
        ):
            raise ValueError(
                "Candidate scores must cover the identical reserved validation documents"
            )
        checks = q["gates"]["checks"]
        q["minimax_gate_ratio"] = max(
            q["pooled_ece"] / checks["pooled_ece"]["target"],
            q["worst_stratum_ece"] / checks["worst_stratum_ece"]["target"],
        )
        return q

    baseline = measure(source.stacker, parent_validation)
    seed = info["seed"]
    fitted = {}
    quality = {"original": {"settings": None, **baseline}}
    y_train = [r.label for r in rows[TRAIN]]
    y_cal = [r.label for r in rows[CALIBRATION]]
    sizes = [r.words for r in rows[CALIBRATION]]
    profiles = [("deep", None, plain, [(31, 0.0, 0.0), (7, 1.0, 0.0)])]
    probe_configs = [(31, 0.0, 0.0), (7, 1.0, 0.0), (7, 1.0, 0.5), (7, 1.0, 0.75)]
    for index, digest in enumerate(sorted(probes), 1):
        label = "probe" if len(probes) == 1 else f"probe-{index}"
        profiles.append((label, digest, inputs[digest], probe_configs))
    for label, digest, x, configs in profiles:
        probe = probes.get(digest)
        for leaves, l2, anchor in configs:
            cls = DeepStacker if probe is None else ProbeDeepStacker
            settings = {"max_leaf_nodes": leaves, "l2_regularization": l2, "probe_anchor": anchor}
            stacker = cls.fit(
                x[TRAIN], y_train, x[CALIBRATION], y_cal, sizes, seed=seed, **settings
            )
            name = f"{label}-leaves{leaves}-anchor{anchor:g}"
            fitted[name] = (stacker, probe)
            quality[name] = {
                "settings": {**settings, "probe_sha256": digest},
                **measure(stacker, x[VALIDATION]),
            }
            if digest is not None:
                probe_reports[digest]["candidates"].append(name)
    # Both ECE measures must improve on the frozen parent. Prefer satisfying both
    # release gates, then minimize the larger gate-relative calibration error.
    eligible = []
    for k in fitted:
        reasons = []
        for metric in ("pooled_ece", "worst_stratum_ece"):
            if quality[k][metric] >= baseline[metric]:
                reasons.append(f"{metric} did not improve")
        for gate, old in baseline["gates"]["checks"].items():
            if gate in {"pooled_ece", "worst_stratum_ece"} or old["status"] != "pass":
                continue
            if quality[k]["gates"]["checks"][gate]["status"] != "pass":
                reasons.append(f"{gate} lost its passing result")
        quality[k]["exclusions"] = reasons
        if not reasons:
            eligible.append(k)

    def rank(k):
        q = quality[k]
        return q["minimax_gate_ratio"], q["pooled_ece"], k

    winner = min(eligible, key=rank) if eligible else "original"
    for details in probe_reports.values():
        best = min(details["candidates"], key=rank)
        details["lowest_minimax_candidate"] = best
        details["minimax_gate_ratio"] = quality[best]["minimax_gate_ratio"]
        qualifying = [k for k in details["candidates"] if k in eligible]
        details["best_admissible_candidate"] = min(qualifying, key=rank) if qualifying else None
    lineage = {
        "frozen_parent_sha256": parent_sha,
        "features_sha256": content_sha,
        "selection_sha256": info["selection_sha256"],
        "effective_selection_sha256": quarantine["effective_selection_sha256"],
        "source_aliases": source_aliases,
        "winner": winner,
        "settings": quality[winner]["settings"],
        "seed": seed,
        "probe_sha256": (quality[winner]["settings"] or {}).get("probe_sha256"),
        "validation_ids_sha256": expected_ids,
    }
    if winner == "original":
        _copy_model(args.model_in, args.model_out)
    else:
        stacker, probe = fitted[winner]
        result = DeepModel(source.heads, stacker, source.identity, probe=probe)
        result.training_scope = source.training_scope
        result.fit_counts = {
            **getattr(source, "fit_counts", {}),
            "stacker": dict(Counter(y_train)),
            "calibration": dict(Counter(y_cal)),
        }
        result.fit_selection = {
            "seed": seed,
            "dataset_order": source.training_scope["dataset_order"],
            "limit_per_class_per_dataset_split": None,
            "quick_prefill": info["quick_prefill"],
            "train_limit_per_class": info["train_limit_per_class"],
            "cal_limit_per_class": info["cal_limit_per_class"],
            "attack_limit_per_class": info["attack_limit_per_class"],
        }
        result.refit_provenance = lineage
        result.save(args.model_out)
    report = {
        "experiment": "frozen-heads-refit",
        "cohort": "validation",
        "selected": winner,
        "selected_model_sha256": sha256(args.model_out),
        "lineage": lineage,
        "cache": info,
        "source_quarantine": quarantine,
        "selection_rule": "Improve both validation ECE measures over the parent and preserve its other passing quality gates. Minimize the larger gate-relative ECE, then pooled ECE. Preserve the parent if no candidate qualifies.",
        "validation_cohort": {
            "seed": seed,
            "limit_per_class_per_dataset_split": info["limit_per_class_per_dataset_split"],
            "documents": len(rows[VALIDATION]),
            "scored_ids_sha256": expected_ids,
            "groups_sha256": digest_strings(sorted({r.group for r in rows[VALIDATION]})),
        },
        "probe_training_provenance": next(iter(probe_reports.values()))["training_provenance"]
        if len(probes) == 1
        else None,
        "probes": probe_reports,
        "refusals": refused,
        "counts": {
            k: {
                "documents": len(v),
                "groups": len({r.group for r in v}),
                "labels": dict(Counter(r.label for r in v)),
            }
            for k, v in rows.items()
        },
        "candidates": quality,
    }
    write_json(report, args.selection_out)
    return {
        "selected": winner,
        "pooled_ece": quality[winner]["pooled_ece"],
        "worst_stratum_ece": quality[winner]["worst_stratum_ece"],
        "model_sha256": report["selected_model_sha256"],
    }
