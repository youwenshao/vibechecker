"""Fit a text-only readout of the frozen Deep encoder on the head-training partition."""

import argparse
import heapq
import json
import os
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from time import monotonic

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.decomposition import PCA
from sklearn.kernel_approximation import Nystroem
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits
from vibechecker_engine.signals import ENCODER_VECTOR_VERSION

from .deep_cohort import fold
from .loaders import examples, fingerprint
from .registry import registry, select, sha256
from .source_groups import human_source_aliases, source_key


def training_sample(stream, count_words, *, source_aliases, seed, human_cap, clean_cap, attack_cap):
    """Use only the original head-training fold; exclude documents and source groups shared with other folds."""
    buckets = defaultdict(list)
    protected, protected_groups, seen = set(), set(), {}
    for item in stream:
        key = fingerprint(item.text)
        group = fingerprint(item.source_group) if item.source_group else key
        if item.split != "train" or fold(item, "head") != 0:
            protected.add(key)
            protected_groups.add(group)
            continue
        if key in seen:
            if seen[key] != item.label:
                protected.add(key)
            continue
        if not 300 <= count_words(item.text) <= 2500:
            continue
        seen[key] = item.label
        cap = human_cap if not item.label else clean_cap if item.attack == "none" else attack_cap
        bucket = buckets[item.dataset, item.generator, item.attack]
        priority = int(fingerprint(f"{seed}/{key}")[:16], 16)
        entry = (-priority, key, group, item)
        if len(bucket) < cap:
            heapq.heappush(bucket, entry)
        elif priority < -bucket[0][0]:
            heapq.heapreplace(bucket, entry)
    # Retain the original reservoir nominations. A quarantined source leaves its
    # slot empty so a fresh fit and a read-only cached fit select the same rows.
    return sorted(
        [
            (key, group, item)
            for bucket in buckets.values()
            for _, key, group, item in bucket
            if key not in protected
            and group not in protected_groups
            and source_key(item, document_id=key) not in source_aliases.groups
        ],
        key=lambda row: row[0],
    )


def open_cache(path, metadata, *, cached_only=False):
    expected = json.dumps(metadata, sort_keys=True)
    if cached_only:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path)
        db.execute(
            "CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK (id=1), value TEXT)"
        )
        db.execute("CREATE TABLE IF NOT EXISTS vectors (digest TEXT PRIMARY KEY, data BLOB)")
        with db:
            db.execute("INSERT OR IGNORE INTO metadata VALUES (1, ?)", (expected,))
    if db.execute("SELECT value FROM metadata WHERE id=1").fetchone() != (expected,):
        db.close()
        raise ValueError("Encoder cache was built with a different extraction profile")
    return db


def collect(chosen, db, load_encoder, *, cached_only=False):
    from vibechecker_engine.text import Refusal, prepare, validate

    rows = []
    encoder = None
    last = monotonic()
    for ix, (key, group, item) in enumerate(chosen, 1):
        cached = db.execute("SELECT data FROM vectors WHERE digest=?", (key,)).fetchone()
        if cached is None:
            if cached_only:
                raise ValueError("The read-only encoder cache is missing a selected training row")
            try:
                doc = prepare(item.text)
                validate(doc, "deep")
                if encoder is None:
                    encoder = load_encoder()
                vector = np.asarray(encoder.evidence(doc.normalized).vector, dtype="<f4")
                if vector.shape != (769,) or not np.isfinite(vector).all():
                    raise ValueError("Invalid frozen encoder representation")
                blob = vector.tobytes()
            except Refusal:
                blob = None
            # Another fit can finish this document while the encoder is running.
            # Consume the committed vector that future resumptions will also see.
            with db:
                db.execute("INSERT OR IGNORE INTO vectors VALUES (?, ?)", (key, blob))
                (blob,) = db.execute("SELECT data FROM vectors WHERE digest=?", (key,)).fetchone()
        else:
            (blob,) = cached
        if blob is not None:
            rows.append(
                (
                    key,
                    group,
                    item.label,
                    f"{item.dataset}/{item.generator}/{item.attack}",
                    np.frombuffer(blob, dtype="<f4"),
                )
            )
        if monotonic() - last >= 45:
            print(f"Encoder head features: {ix}/{len(chosen)} screened", flush=True)
            last = monotonic()
    return rows


def _source_folds(groups, seed, tag, count):
    return np.asarray(
        [int(fingerprint(f"{tag}/{seed}/{group}")[:8], 16) % count for group in groups]
    )


def _svm_calibration_splits(groups, labels, seed):
    # All variations on a source passage stay together. The sigmoid receives
    # out-of-fold margins, and each clone learns scaling and PCA on its own fold.
    groups = np.asarray(groups)
    fold_ids = _source_folds(groups, seed, "bounded-probe-oof", 3)
    splits = []
    for fold_id in range(3):
        train, val = np.flatnonzero(fold_ids != fold_id), np.flatnonzero(fold_ids == fold_id)
        if any(set(labels[idx]) != {0, 1} for idx in (train, val)):
            raise ValueError("Each margin-calibration fold requires both labels")
        if set(groups[train]) & set(groups[val]):
            raise ValueError("Source groups overlap in margin calibration")
        splits.append((train, val))
    return splits


def _svm(groups, labels, width, seed):
    splits = _svm_calibration_splits(groups, labels, seed)
    dims = min(64, width, min(len(tr) - 1 for tr, _ in splits))
    pipeline = make_pipeline(
        StandardScaler(),
        PCA(n_components=dims, whiten=True, random_state=seed),
        SVC(
            C=16.0,
            gamma=0.5 / dims,
            kernel="rbf",
            class_weight="balanced",
            cache_size=300,
            random_state=seed,
        ),
    )
    return CalibratedClassifierCV(pipeline, method="sigmoid", cv=splits, ensemble=False, n_jobs=1)


def _canonical_candidates(rows, width, seed):
    def linear(c):
        return LogisticRegression(C=c, class_weight="balanced", max_iter=600, random_state=seed)

    candidates = [
        (f"logistic-{c}", make_pipeline(StandardScaler(), linear(c))) for c in (0.01, 0.1, 1)
    ]
    # The nonlinear readout can separate clusters of writing styles in the same frozen representation.
    dims = min(64, rows - 1, width)
    candidates.append(
        (
            "rbf",
            make_pipeline(
                StandardScaler(),
                PCA(n_components=dims, whiten=True, random_state=seed),
                Nystroem(gamma=0.5 / dims, n_components=min(512, rows), random_state=seed),
                linear(16.0),
            ),
        )
    )
    return candidates


def _calibration_error(y, p):
    bins = np.clip((p * 10).astype(int), 0, 9)
    return float(np.abs(np.bincount(bins, weights=y - p, minlength=10)).sum() / len(y))


def _svm_diagnostics(y, p, strata):
    by_stratum = {}
    for s in np.unique(strata):
        mask = strata == s
        by_stratum[str(s)] = {
            "n": int(mask.sum()),
            "errors_at_half": int(((p[mask] >= 0.5) != y[mask]).sum()),
            "ece_10_bins": _calibration_error(y[mask], p[mask]),
        }
    return {
        "ece_10_bins": _calibration_error(y, p),
        "worst_ece_n5": max(
            (v["ece_10_bins"] for v in by_stratum.values() if v["n"] >= 5), default=None
        ),
        "human_n": int((y == 0).sum()),
        "human_false_positives_at_half": int(((y == 0) & (p >= 0.5)).sum()),
        "errors_at_half": int(((p >= 0.5) != y).sum()),
        "by_stratum": by_stratum,
    }


def fit(rows, seed, *, candidate="canonical"):
    # All inner validation groups are drawn from the training partition.
    groups = np.asarray([row[1] for row in rows])
    dev = _source_folds(groups, seed, "probe-validation", 5) == 0
    y = np.array([r[2] for r in rows])
    x = np.stack([r[4] for r in rows])
    strata = np.array([r[3] for r in rows])[dev]
    if any(set(y[mask]) != {0, 1} for mask in (dev, ~dev)):
        raise ValueError("Both training and development need both labels")
    if set(groups[~dev]) & set(groups[dev]):
        raise ValueError("Source groups overlap in probe development")
    if candidate == "canonical":
        candidates = _canonical_candidates((~dev).sum(), x.shape[1], seed)
    elif candidate == "svm-c16":
        candidates = [(candidate, _svm(groups[~dev], y[~dev], x.shape[1], seed))]
    else:
        raise ValueError("Unknown encoder probe candidate")
    results = []
    for name, estimator in candidates:
        estimator.fit(x[~dev], y[~dev])
        p = estimator.predict_proba(x[dev])[:, 1]
        losses = [
            log_loss(y[dev][mask], p[mask], labels=[0, 1])
            for s in np.unique(strata)
            if (mask := strata == s).sum() >= 5
        ]
        results.append(
            {
                "name": name,
                "auroc": float(roc_auc_score(y[dev], p)),
                "log_loss": log_loss(y[dev], p),
                "macro_log_loss": float(np.mean(losses)) if losses else log_loss(y[dev], p),
                **(_svm_diagnostics(y[dev], p, strata) if name == "svm-c16" else {}),
            }
        )
    best = min(
        range(len(results)), key=lambda i: (results[i]["macro_log_loss"], results[i]["log_loss"])
    )
    name, model = candidates[best]
    protocol = {}
    if name == "svm-c16":
        # Fold indices above are relative to the inner training matrix. Rebuild
        # them for the final supervised fit on the complete head-training fold.
        model = _svm(groups, y, x.shape[1], seed)
        protocol = {
            "method": "exact-rbf-svm",
            "pca_dimensions": model.estimator.steps[1][1].n_components,
            "C": 16,
            "gamma": model.estimator.steps[-1][1].gamma,
            "margin_calibration": "3-source-group-fold sigmoid",
            "fold_hash_tag": "bounded-probe-oof",
        }
    return model.fit(x, y), {
        "selected": name,
        "inner_train_n": int((~dev).sum()),
        "inner_validation_n": int(dev.sum()),
        "inner_train_groups": len(set(groups[~dev])),
        "inner_validation_groups": len(set(groups[dev])),
        "inner_train_group_ids_sha256": fingerprint(" ".join(sorted(set(groups[~dev])))),
        "inner_validation_group_ids_sha256": fingerprint(" ".join(sorted(set(groups[dev])))),
        "candidates": results,
        **protocol,
    }


def main(argv=None):
    from vibechecker_engine.signals import Encoder
    from vibechecker_engine.stacker import save_artifact
    from vibechecker_engine.text import count_words

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("eval/.cache"))
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--model-out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--datasets", nargs="+", default=["raid", "raid-attacks", "asap", "ellipse", "liang"]
    )
    parser.add_argument("--human-cap", type=int, default=1200)
    parser.add_argument("--clean-cap", type=int, default=320)
    parser.add_argument("--attack-cap", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--candidate", choices=("canonical", "svm-c16"), default="canonical")
    parser.add_argument(
        "--cached-only",
        action="store_true",
        help="Read an existing complete feature cache without loading the encoder",
    )
    parser.add_argument("--commercial-only", action="store_true")
    args = parser.parse_args(argv)
    if len({p.resolve() for p in (args.features, args.model_out, args.report)}) != 3:
        parser.error("The feature cache, model and report must use distinct paths")
    if min(args.human_cap, args.clean_cap, args.attack_cap) < 1:
        parser.error("Reservoir caps must be positive")
    selected = select(registry(), args.datasets, args.commercial_only)
    manifest = {
        d.id: {"version": d.version, "sha256": [a.sha256 for a in d.artifacts]} for d in selected
    }
    aliases = human_source_aliases(examples(selected, args.cache))
    chosen = training_sample(
        examples(selected, args.cache),
        count_words,
        source_aliases=aliases,
        seed=args.seed,
        human_cap=args.human_cap,
        clean_cap=args.clean_cap,
        attack_cap=args.attack_cap,
    )
    print(f"Selected {len(chosen)} training documents before language screening", flush=True)
    path = Path(os.environ["VIBECHECKER_ENCODER"])
    profile = {
        "vector_version": ENCODER_VECTOR_VERSION,
        "backend": os.environ["VIBECHECKER_BACKEND"],
        "encoder_files": {
            p.name: sha256(p)
            for p in sorted(path.iterdir())
            if p.is_file() and p.suffix in {".json", ".safetensors", ".txt", ".model", ".jinja"}
        },
        "quick_prefill": int(os.environ.get("VIBECHECKER_QUICK_PREFILL", "64")),
    }

    def load_encoder():
        encoder = Encoder.load(path, profile["backend"])
        encoder.batch_windows = 1 if profile["quick_prefill"] == 64 else 2
        return encoder

    db = open_cache(args.features, profile, cached_only=args.cached_only)
    try:
        rows = collect(chosen, db, load_encoder, cached_only=args.cached_only)
    finally:
        db.close()
    with threadpool_limits(limits=2):
        estimator, scores = fit(rows, args.seed, candidate=args.candidate)
    provenance = {
        **profile,
        "encoder_sha256": profile["encoder_files"]["model.safetensors"],
        "manifest": manifest,
        "partition": "train",
        "source_aliases": aliases.summary(),
        "source_alias_reservoir": "exclude nominated source groups without replacement",
        "head_fold": 0,
        "commercial_only": args.commercial_only,
        "seed": args.seed,
        "fit_group_ids_sha256": fingerprint(" ".join(sorted({r[1] for r in rows}))),
        "fit_document_ids_sha256": fingerprint(" ".join(sorted(r[0] for r in rows))),
        "fit_counts": dict(sorted(Counter(r[3] for r in rows).items())),
        "sampling_caps": {
            "human": args.human_cap,
            "clean_machine": args.clean_cap,
            "attacked_machine": args.attack_cap,
        },
        "selection": scores,
    }
    estimator.training_provenance_ = provenance
    save_artifact(estimator, args.model_out)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(provenance, indent=2, allow_nan=False) + "\n", encoding="utf8"
    )
    print(json.dumps({"documents": len(rows), **scores}, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
