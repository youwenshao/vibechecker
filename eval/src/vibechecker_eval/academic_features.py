"""Extract numeric evidence for the previously registered auxiliary academic development cohort."""

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

import joblib
import numpy as np

from .academic_development import resolve
from .deep_runner import _progress, write_json
from .refit_cache import digest_strings, runtime_identity, same_numeric_runtime
from .registry import sha256
from .rewrite_sidecar import finite


def verify_cache(db, rows, complete=False):
    """Check each resumed member, its order and the original four input bindings."""
    accepted = {}
    content = hashlib.sha256()
    kinds = Counter()
    for rowno, key, group, kind, domain, generator, words, features, vector in db.execute(
        "SELECT * FROM documents ORDER BY rowno"
    ):
        if not 0 <= rowno < len(rows):
            raise ValueError("Academic cache has an unregistered document position")
        member = rows[rowno]
        if (key, group, kind, domain, generator) != tuple(
            member[k] for k in ("id", "group", "kind", "domain", "generator")
        ):
            raise ValueError("Academic numeric cache membership differs from registration")
        if not 300 <= words <= 2500:
            raise ValueError("Academic numeric cache length differs from production bounds")
        finite(np.frombuffer(features, dtype="<f8"), 13, "<f8")
        finite(np.frombuffer(vector, dtype="<f4"), 769, "<f4")
        content.update(
            json.dumps(
                [rowno, key, group, kind, domain, generator, words], separators=(",", ":")
            ).encode()
        )
        content.update(features)
        content.update(vector)
        accepted[key] = rowno
        kinds[kind] += 1
    if complete and len(accepted) != len(rows):
        raise ValueError("Incomplete academic development cache")
    return accepted, content.hexdigest(), dict(kinds)


def collect(args):
    from vibechecker_engine.deep import DEEP_FEATURE_NAMES, DeepExtractor, DeepModel
    from vibechecker_engine.signals import ENCODER_VECTOR_VERSION

    source = json.loads(args.prior_report.read_bytes())
    plan = json.loads(args.plan.read_bytes())
    registration = plan["provenance"]
    rows = resolve(source, args.cache, args.base_features)
    members = [{k: v for k, v in row.items() if k != "text"} for row in rows]
    if (
        members != plan["members"]
        or registration["prior_report_sha256"] != sha256(args.prior_report)
        or digest_strings(json.dumps(r, sort_keys=True) for r in members)
        != registration["plan_sha256"]
    ):
        raise ValueError("Private membership plan does not match the frozen development commitment")
    protocol = json.loads(args.selection.read_bytes())["protocol"]
    if (
        sha256(args.parent) != protocol["base_model_sha256"]
        or protocol["backend"] != "mlx-metal"
        or protocol["quick_prefill"] != 512
        or list(DEEP_FEATURE_NAMES) != protocol["feature_names"]
        or protocol["encoder_vector"] != ENCODER_VECTOR_VERSION
    ):
        raise ValueError(
            "Expected the original Metal/512 calibration parent, heads and feature schema"
        )
    parent = DeepModel.load(args.parent)
    runtime = runtime_identity()
    if not same_numeric_runtime(protocol["base_runtime"], runtime):
        raise ValueError("Academic numeric runtime differs from original cache")
    provenance = {
        "scheme": "frozen-academic-development-numeric-v1",
        "registration": registration,
        "member_order": "ascending normalized document SHA256",
        "ordered_groups_sha256": digest_strings(r["group"] for r in members),
        "ordered_document_ids_sha256": digest_strings(r["id"] for r in members),
        "prior_report_sha256": sha256(args.prior_report),
        "plan_file_sha256": sha256(args.plan),
        "selection_file_sha256": sha256(args.selection),
        "parent_sha256": protocol["base_model_sha256"],
        "heads_joblib_hash": joblib.hash(parent.heads),
        "weights": parent.identity,
        "backend": protocol["backend"],
        "quick_prefill": protocol["quick_prefill"],
        "feature_names": protocol["feature_names"],
        "encoder_vector": ENCODER_VECTOR_VERSION,
        "runtime": runtime,
    }
    args.sidecar.parent.mkdir(parents=True, exist_ok=True)
    if args.sidecar.resolve() in {
        p.resolve()
        for p in (
            args.prior_report,
            args.plan,
            args.base_features,
            args.selection,
            args.parent,
            args.out,
        )
    }:
        raise ValueError("Academic numeric sidecar must use a separate path")
    with sqlite3.connect(args.sidecar) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS meta(id INTEGER PRIMARY KEY CHECK(id=1), provenance TEXT NOT NULL,complete INTEGER NOT NULL,content_sha256 TEXT)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS documents(rowno INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,source TEXT NOT NULL,kind TEXT NOT NULL,domain TEXT NOT NULL,generator TEXT NOT NULL,words INTEGER NOT NULL,features BLOB NOT NULL,encoder BLOB NOT NULL)"
        )
        encoded = json.dumps(provenance, sort_keys=True)
        with db:
            db.execute("INSERT OR IGNORE INTO meta VALUES(1,?,0,NULL)", (encoded,))
        old, complete, expected = db.execute(
            "SELECT provenance,complete,content_sha256 FROM meta"
        ).fetchone()
        if old != encoded:
            raise ValueError("Academic cache provenance differs")
        have, digest, kinds = verify_cache(db, rows, complete=bool(complete))
        if complete and digest != expected:
            raise ValueError("Academic cache completed content digest differs")
        pending = [(i, row) for i, row in enumerate(rows) if row["id"] not in have]
        if pending:
            extractor = DeepExtractor.from_env(include_encoder_evidence=True)
            parent.verify(extractor)
            if (
                extractor.backend != protocol["backend"]
                or extractor.quick.lm.chunk_size != protocol["quick_prefill"]
            ):
                raise ValueError("Expected the original Metal/512 extraction profile")
            for i, row in _progress(
                "Independent academic development features", pending, len(pending)
            ):
                raw = extractor.extract(row["text"])
                features = finite(
                    parent.heads.features(raw), len(DEEP_FEATURE_NAMES), "<f8"
                ).tobytes()
                evidence = finite(raw.encoder_vector, 769, "<f4").tobytes()
                with db:
                    db.execute(
                        "INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            i,
                            row["id"],
                            row["group"],
                            row["kind"],
                            row["domain"],
                            row["generator"],
                            raw.quick.word_count,
                            features,
                            evidence,
                        ),
                    )
            _, digest, kinds = verify_cache(db, rows, complete=True)
        with db:
            db.execute("UPDATE meta SET complete=1,content_sha256=? WHERE id=1", (digest,))
    write_json(
        {
            "provenance": provenance,
            "documents": len(rows),
            "groups": len({r["group"] for r in members}),
            "kinds": kinds,
            "content_sha256": digest,
            "sidecar_sha256": sha256(args.sidecar),
            "candidate_predictions_computed": False,
        },
        args.out,
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "prior-report",
        "plan",
        "cache",
        "base-features",
        "selection",
        "parent",
        "sidecar",
        "out",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    collect(p.parse_args(argv))


if __name__ == "__main__":
    main()
