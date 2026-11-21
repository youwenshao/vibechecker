"""Resumable numeric Deep features for stacker fitting and a separate validation comparison."""

import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from importlib import metadata
from pathlib import Path

import numpy as np

from .deep_cohort import fold
from .deep_runner import _progress
from .loaders import examples, fingerprint
from .metrics import length_bin
from .registry import sha256
from .runner import sample

TRAIN, CALIBRATION, VALIDATION = 0, 1, 2


def role(item):
    if item.split == "train" and fold(item, "head") == 1:
        return TRAIN
    if item.split == "calibration":
        return CALIBRATION
    if item.split == "test" and fold(item, "bakeoff") == 0:
        return VALIDATION
    return None


def stratum_names(item, words):
    names = [
        f"{field}/{getattr(item, field)}"
        for field in ("split", "dataset", "genre", "writer", "generator", "attack")
    ]
    names.append("length/" + length_bin(words))
    if item.genre == "essay" and item.writer == "ESL":
        names.append("fairness/ESL-essay")
    return names


def strata(item, words):
    return sorted(fingerprint(name) for name in stratum_names(item, words))


def digest_strings(values):
    result = hashlib.sha256()
    for value in values:
        result.update(value.encode())
        result.update(b"\n")
    return result.hexdigest()


def runtime_identity():
    import vibechecker_engine

    root = Path(vibechecker_engine.__file__).parent
    # Bind resumptions to the code computing these numeric rows, including text and token reductions.
    files = [root / f for f in ("signals.py", "heads.py", "deep.py", "text.py")] + sorted(
        (root / "backends").glob("*.py")
    )
    implementation = digest_strings(
        str(f.relative_to(root).as_posix())
        + ":"
        + hashlib.sha256(f.read_text(encoding="utf8").encode()).hexdigest()
        for f in files
    )
    packages = {}
    for name in ("mlx", "mlx-lm", "torch", "transformers", "numpy", "scikit-learn"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return {"engine_source_sha256": implementation, "packages": packages}


def _initialize(db, provenance):
    db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    encoded = json.dumps(provenance, sort_keys=True, separators=(",", ":"))
    db.execute("INSERT OR IGNORE INTO meta VALUES ('provenance', ?)", (encoded,))
    (stored,) = db.execute("SELECT value FROM meta WHERE key='provenance'").fetchone()
    if stored != encoded:
        raise ValueError(
            "Feature cache provenance differs; use a separate cache for this selection or profile"
        )
    db.execute("""CREATE TABLE IF NOT EXISTS source_groups (
        id TEXT PRIMARY KEY, role INTEGER NOT NULL CHECK (role IN (0,1,2)), UNIQUE(id, role))""")
    db.execute("""CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, group_id TEXT NOT NULL, role INTEGER NOT NULL,
        label INTEGER NOT NULL CHECK (label IN (0,1)), words INTEGER NOT NULL,
        strata TEXT NOT NULL, features BLOB, encoder BLOB, refusal INTEGER,
        CHECK ((features IS NOT NULL AND refusal IS NULL) OR (features IS NULL AND refusal IS NOT NULL)),
        FOREIGN KEY(group_id, role) REFERENCES source_groups(id, role))""")


def plan_rows(args, datasets, count_words):
    # Keep only opaque identifiers on the first pass. A generator/attack bucket can
    # nominate one representative per prompt, including when RAID supplies many variants.
    strata_groups = defaultdict(lambda: defaultdict(dict))
    group_roles = {}
    doc_roles = {}
    excluded_groups, excluded_docs = set(), set()

    def nominate(item, _words, doc_id, duplicate):
        part = role(item)
        group = fingerprint(item.source_group or doc_id)
        partition = part if part is not None else item.split
        if group_roles.setdefault(group, partition) != partition:
            excluded_groups.add(group)
        if doc_roles.setdefault(doc_id, (partition, item.label)) != (partition, item.label):
            excluded_docs.add(doc_id)
        if not duplicate and part in (TRAIN, CALIBRATION):
            nominations = strata_groups[part, item.dataset, item.label][item.generator, item.attack]
            priority = fingerprint(f"{args.seed}:{doc_id}")
            if group not in nominations or priority < nominations[group][0]:
                nominations[group] = (priority, doc_id)

    validation_sample, _ = sample(
        examples(datasets, args.cache),
        args.limit_per_class,
        args.seed,
        count_words,
        length_range=(300, 2500),
        on_eligible=nominate,
    )
    selected = {}
    for item, n in validation_sample:
        if role(item) == VALIDATION:
            key = fingerprint(item.text)
            selected[key] = (fingerprint(item.source_group or key), VALIDATION, item, n)
    del validation_sample
    # A duplicate discovered late in an eval-only source must revoke the earlier
    # fit nomination as well. Keep the independently frozen validation reservoir unchanged.
    print(
        f"Excluded conflicts from fitting: {len(excluded_groups)} source groups, "
        f"{len(excluded_docs)} document hashes",
        file=sys.stderr,
        flush=True,
    )
    doc_roles.clear()
    ids = set()
    for (part, dataset, _label), buckets in sorted(strata_groups.items()):
        limit = args.train_limit_per_class if part == TRAIN else args.cal_limit_per_class
        limit = args.limit_per_class if limit is None else limit
        stages = [
            iter(
                sorted(
                    (priority, group, doc)
                    for group, (priority, doc) in variants.items()
                    if group not in excluded_groups and doc not in excluded_docs
                )
            )
            for _, variants in sorted(
                buckets.items(), key=lambda b: fingerprint(f"{args.seed}:{b[0]}")
            )
        ]
        cap = limit or sum(map(len, buckets.values()))
        if dataset == "raid-attacks" and args.attack_limit_per_class is not None:
            cap = min(cap, args.attack_limit_per_class)
        groups = set()
        while stages and len(groups) < cap:
            continuing = []
            for stage in stages:
                row = next((r for r in stage if r[1] not in groups), None)
                if row is not None:
                    _, group, doc_id = row
                    groups.add(group)
                    ids.add(doc_id)
                    continuing.append(stage)
                if len(groups) == cap:
                    break
            stages = continuing
    strata_groups.clear()
    group_roles.clear()
    # Read text only for the selected fit groups; test selection above exactly matches deep --cohort validation.
    for item in examples(datasets, args.cache):
        key = fingerprint(item.text)
        if key in ids and role(item) in (TRAIN, CALIBRATION):
            selected[key] = (
                fingerprint(item.source_group or key),
                role(item),
                item,
                count_words(item.text),
            )
            ids.remove(key)
            if not ids:
                break
    if ids:
        raise ValueError("A selected source record could not be reread")
    return selected


def collect(args, datasets):
    from vibechecker_engine.deep import DEEP_FEATURE_NAMES, DeepExtractor, DeepModel
    from vibechecker_engine.signals import ENCODER_VECTOR_VERSION
    from vibechecker_engine.text import Refusal, count_words

    paths = (args.features, args.model_in)
    if paths[0].resolve() == paths[1].resolve():
        raise ValueError("Use a separate SQLite feature-cache path")
    source = DeepModel.load(args.model_in)
    manifest = {
        d.id: {"version": d.version, "sha256": [a.sha256 for a in d.artifacts]} for d in datasets
    }
    scope = {
        "manifest": manifest,
        "dataset_order": [d.id for d in datasets],
        "weights": source.identity,
        "commercial_only": args.commercial_only,
    }
    if getattr(source, "training_scope", None) != scope:
        raise ValueError(
            "Frozen heads require their original verified dataset, licensing and weight scope"
        )
    include_encoder = not args.without_encoder_vectors
    if getattr(source, "probe", None) is not None and not include_encoder:
        raise ValueError("The parent model's probe needs cached encoder evidence")
    selected = plan_rows(args, datasets, count_words)
    shapes = {part for _, part, _, _ in selected.values()}
    if shapes != {TRAIN, CALIBRATION, VALIDATION}:
        raise ValueError(
            "Stacker train, calibration and independent validation documents are required"
        )
    extractor = DeepExtractor.from_env(include_encoder_evidence=include_encoder)
    source.verify(extractor)
    provenance = {
        "schema": 1,
        "frozen_parent_sha256": sha256(args.model_in),
        "training_scope": scope,
        "backend": extractor.backend,
        "quick_prefill": extractor.quick.lm.chunk_size,
        "seed": args.seed,
        "limit_per_class_per_dataset_split": args.limit_per_class,
        "train_limit_per_class": args.train_limit_per_class
        if args.train_limit_per_class is not None
        else args.limit_per_class,
        "cal_limit_per_class": args.cal_limit_per_class
        if args.cal_limit_per_class is not None
        else args.limit_per_class,
        "attack_limit_per_class": args.attack_limit_per_class,
        "selected_by_role_source_label_generator_attack": dict(
            sorted(
                Counter(
                    f"{part}/{item.dataset}/{item.label}/{item.generator}/{item.attack}"
                    for _, part, item, _ in selected.values()
                ).items()
            )
        ),
        "feature_names": list(DEEP_FEATURE_NAMES),
        "encoder_vector": ENCODER_VECTOR_VERSION if include_encoder else None,
        "selection_sha256": digest_strings(
            f"{key} {group} {part} {item.label} {n}"
            for key, (group, part, item, n) in sorted(selected.items())
        ),
        "selected": len(selected),
        "runtime": runtime_identity(),
    }
    args.features.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(args.features, timeout=30)
    try:
        db.execute("PRAGMA foreign_keys = ON")
        with db:
            _initialize(db, provenance)
            names = {name for _, _, item, n in selected.values() for name in stratum_names(item, n)}
            db.execute(
                "INSERT OR REPLACE INTO meta VALUES ('strata', ?)",
                (json.dumps({fingerprint(name): name for name in sorted(names)}),),
            )
        cached = {key for (key,) in db.execute("SELECT id FROM documents")}
        if not cached.issubset(selected):
            raise ValueError("Cache contains documents outside its selection")
        missing = [key for key in selected if key not in cached]
        print(
            f"Resuming {len(cached)} cached documents, {len(missing)} remaining",
            file=sys.stderr,
            flush=True,
        )
        for key in _progress("Frozen features", missing, len(missing)):
            group, part, item, n = selected[key]
            features = encoder = refusal = None
            try:
                raw = extractor.extract(item.text)
                x = np.asarray(source.heads.features(raw), dtype="<f8")
                if x.shape != (len(DEEP_FEATURE_NAMES),) or not np.isfinite(x).all():
                    raise ValueError("Invalid stacker feature row")
                features = x.tobytes()
                if include_encoder:
                    vector = np.asarray(raw.encoder_vector, dtype="<f4")
                    if vector.shape != (769,) or not np.isfinite(vector).all():
                        raise ValueError("Expected a finite 769-value ModernBERT document vector")
                    encoder = vector.tobytes()
            except Refusal as exc:
                refusal = {"too_short": 1, "too_long": 2, "not_english": 3}[exc.code]
            with db:
                db.execute("INSERT OR IGNORE INTO source_groups VALUES (?,?)", (group, part))
                db.execute(
                    "INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        key,
                        group,
                        part,
                        item.label,
                        n,
                        json.dumps(strata(item, n)),
                        features,
                        encoder,
                        refusal,
                    ),
                )
        with db:
            (count,) = db.execute("SELECT COUNT(*) FROM documents").fetchone()
            if count != len(selected):
                raise ValueError("Incomplete feature cache")
            db.execute("INSERT OR REPLACE INTO meta VALUES ('complete', '1')")
        return {
            "selected": count,
            "resumed": len(cached),
            "accepted": db.execute(
                "SELECT COUNT(*) FROM documents WHERE features IS NOT NULL"
            ).fetchone()[0],
        }
    finally:
        db.close()
