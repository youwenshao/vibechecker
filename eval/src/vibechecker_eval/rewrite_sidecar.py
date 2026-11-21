"""Paired book/news rewrites for document stacker fitting and independent development stress."""

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np

from .deep_cohort import fold
from .deep_runner import _progress
from .encoder_probe import training_sample
from .loaders import examples, fingerprint
from .refit import CachedRow, eligible_fit_rows, load_rows
from .refit_cache import CALIBRATION, TRAIN, VALIDATION, digest_strings, runtime_identity
from .registry import registry, select, sha256
from .runner import sample
from .source_groups import human_source_aliases, source_key

ROLES = ("head", "stack", "calibration", "stress")
DOMAINS = ("books", "news")
STRESS = 3
ROLE_ID = {"stack": TRAIN, "calibration": CALIBRATION, "stress": STRESS}


def metadata_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def base_models(args):
    from vibechecker_engine.deep import DeepModel

    parent, incumbent = (DeepModel.load(p) for p in (args.parent, args.incumbent))
    p_sha, i_sha = sha256(args.parent), sha256(args.incumbent)
    selection = json.loads(args.incumbent_selection.read_bytes())
    lineage = getattr(incumbent, "refit_provenance", {})
    if (
        selection["selected_model_sha256"] != i_sha
        or selection["lineage"] != lineage
        or lineage.get("frozen_parent_sha256") != p_sha
        or incumbent.probe is None
        or not parent.training_scope
        or parent.training_scope != incumbent.training_scope
        or parent.training_scope["commercial_only"]
        or parent.identity != incumbent.identity
        or joblib.hash(parent.heads) != joblib.hash(incumbent.heads)
    ):
        raise ValueError("Expected the frozen original heads and their research-scope v2 incumbent")
    info, rows, names, _, content_sha = load_rows(args.features, parent, p_sha, False)
    if (
        content_sha != lineage["features_sha256"]
        or info["quick_prefill"] != 512
        or info["backend"] != "mlx-metal"
        or info["selection_sha256"] != lineage["selection_sha256"]
    ):
        raise ValueError("Original numeric cache or Metal/512 extraction provenance differs")
    rows, quarantine = eligible_fit_rows(info, rows, args.cache)
    if (
        quarantine["effective_selection_sha256"] != lineage["effective_selection_sha256"]
        or quarantine["source_aliases"] != lineage["source_aliases"]
        or set(rows) != {TRAIN, CALIBRATION, VALIDATION}
        or len(rows[VALIDATION]) != selection["validation_cohort"]["documents"]
        or fingerprint(" ".join(sorted(r.id for r in rows[VALIDATION])))
        != lineage["validation_ids_sha256"]
    ):
        raise ValueError("Original effective fitting or live validation cohort differs")
    for name in ("genre/essay", "fairness/ESL-essay", "dataset/liang/toefl", "writer/native_proxy"):
        names.setdefault(fingerprint(name), name)
    return parent, incumbent, selection, info, rows, names


def legacy_members(args, info, incumbent, desired):
    """Conservative, pre-language envelopes; no historical/future scores or labels consumed as outcomes."""
    from vibechecker_engine.text import count_words

    scope = info["training_scope"]
    datasets = select(registry(), scope["dataset_order"])
    with sqlite3.connect(args.features.resolve().as_uri() + "?mode=ro", uri=True) as db:
        base = list(db.execute("SELECT id, group_id, role FROM documents"))
    old = defaultdict(lambda: (set(), set()))
    for key, group, role in base:
        ids, groups = old[
            {TRAIN: "stack", CALIBRATION: "calibration", VALIDATION: "protected"}[role]
        ]
        ids.add(key)
        groups.add(group)
    candidate_ids, candidate_groups = desired

    def identities(record, kind):
        key = fingerprint(record.text)
        group = fingerprint(source_key(record, document_id=key))
        old[kind][0].add(key)
        old[kind][1].add(group)

    def checked_stream():
        for record in examples(datasets, args.cache):
            if record.split == "test":
                key = fingerprint(record.text)
                group = fingerprint(source_key(record, document_id=key))
                # Every test partition is unavailable to a supplement role, including
                # validations outside a reservoir and duplicate texts under other IDs.
                if key in candidate_ids or group in candidate_groups:
                    old["protected"][0].add(key)
                    old["protected"][1].add(group)
            yield record

    # Phase 1 v1 had no fit_selection field. Its documented training reservoir was 16/42.
    fitted, _ = sample(checked_stream(), 16, 42, count_words, length_range=(300, 2500))
    for r, _ in fitted:
        if r.split == "train":
            identities(r, "head" if fold(r, "head") == 0 else "stack")
        elif r.split == "calibration":
            identities(r, "calibration")
    historical, _ = sample(
        examples(datasets, args.cache), 72, 42, count_words, length_range=(300, 2500)
    )
    final = [r for r, _ in historical if r.split == "test" and fold(r, "bakeoff") == 1]
    if (
        len(final) != 266
        or fingerprint(" ".join(sorted(fingerprint(r.text) for r in final)))
        != "9a8891ffebd90349ecbe07c0c42216b48a14305389e462f21c7e9407d13f3a91"
    ):
        raise ValueError("Historical 266-document envelope could not be verified")
    for item in final:
        identities(item, "protected")
    from .prospective import plan_digest

    plan = json.loads(args.prospective_plan.read_bytes())
    if (
        plan_digest(plan) != "98e100bdc12a14cefbe35c88f6b48397577e4f11388978c007dbdea6aabaf170"
        or plan["input_manifest"] != scope["manifest"]
    ):
        raise ValueError("Unknown prospective final reservation")
    for key, group in plan["members"]:
        old["protected"][0].add(key)
        old["protected"][1].add(group)
    provenance = incumbent.probe.training_provenance_
    caps = provenance["sampling_caps"]
    # An over-inclusive pre-language, pre-alias envelope avoids accessing any probe predictions.
    for key, _, item in training_sample(
        examples(datasets, args.cache),
        count_words,
        source_aliases=human_source_aliases(()),
        seed=provenance["seed"],
        human_cap=caps["human"],
        clean_cap=caps["clean_machine"],
        attack_cap=caps["attacked_machine"],
    ):
        old["head"][0].add(key)
        old["head"][1].add(fingerprint(source_key(item, document_id=key)))
    return old


def pair_docs(pair):
    return (pair.human, pair.machine, pair.clean_human, pair.clean_machine)


def select_pairs(by_role, legacy, cap, seed):
    docs, groups = {}, {}
    pooled = defaultdict(list)
    excluded = Counter()
    for role in ROLES:
        for pair in by_role[role]:
            group = fingerprint(pair.source_group)
            if role != pair.role or group in groups:
                raise ValueError("Duplicate source or role mismatch in paired supplement")
            groups[group] = role
            ids = set()
            for d in pair_docs(pair):
                if (
                    not d
                    or d.id != fingerprint(d.text)
                    or d.id in ids
                    or docs.setdefault(d.id, group) != group
                ):
                    raise ValueError(
                        "Supplement documents must be unique within a pair and disjoint across roles"
                    )
                ids.add(d.id)
            rewritten = {pair.human.id, pair.machine.id}
            if any(
                group in legacy_groups or ids & legacy_ids
                for old_role, (legacy_ids, legacy_groups) in legacy.items()
                if old_role != role
            ):
                if role == "head":
                    raise ValueError(
                        "Supplemental probe head role overlaps protected legacy membership"
                    )
                excluded[f"{role}/{pair.domain}/cross_role"] += 1
                continue
            if role == "head" or pair.domain not in DOMAINS:
                continue
            if rewritten & legacy[role][0]:
                excluded[f"{role}/{pair.domain}/already_cached"] += 1
                continue
            if not all(300 <= d.words <= 2500 for d in (pair.human, pair.machine)):
                excluded[f"{role}/{pair.domain}/length"] += 1
                continue
            pooled[role, pair.domain].append(
                (fingerprint(f"rewrite-sidecar-v1/{seed}/{group}"), group, pair)
            )
    selected = []
    for role in ROLE_ID:
        for domain in DOMAINS:
            ranked = sorted(pooled[role, domain], key=lambda value: value[:2])
            if not ranked:
                raise ValueError(f"No independent paired rewrite groups remain for {role}/{domain}")
            selected.extend(p for _, _, p in ranked[:cap])
    return selected, dict(sorted(excluded.items())), set(docs), set(groups)


def inputs(args):
    from .rewrite_data import load_rewrite_pairs, rewrite_provenance

    if not 48 <= args.groups_per_domain <= 64:
        raise ValueError("Use a fixed group cap between 48 and 64 per domain and role")
    if sha256(args.supplement) != args.supplement_sha256:
        raise ValueError("Verified supplement file digest differs")
    parent, incumbent, selection, info, rows, names = base_models(args)
    provenance = rewrite_provenance(args.supplement)
    by_role = {
        role: load_rewrite_pairs(args.supplement, role=role, commercial_only=False)
        for role in ROLES
    }
    desired_ids = {d.id for pairs in by_role.values() for p in pairs for d in pair_docs(p) if d}
    desired_groups = {fingerprint(p.source_group) for pairs in by_role.values() for p in pairs}
    old = legacy_members(args, info, incumbent, (desired_ids, desired_groups))
    selected, excluded, all_ids, all_groups = select_pairs(
        by_role, old, args.groups_per_domain, args.seed
    )
    for ids, groups in old.values():
        all_ids.update(ids)
        all_groups.update(groups)
    members = {}
    for p in selected:
        group = fingerprint(p.source_group)
        for label, d in enumerate([p.human, p.machine]):
            if d.id in members:
                raise ValueError("Duplicate selected rewrite document")
            members[d.id] = (group, p.role, p.domain, label, d)
    expected = {key: [*v[:4], v[4].words] for key, v in members.items()}
    selected_counts = Counter(f"{p.role}/{p.domain}" for p in selected)
    protocol = {
        "schema": "paired-deep-rewrite-sidecar-v1",
        "seed": args.seed,
        "groups_per_domain_role": args.groups_per_domain,
        "base_model_sha256": sha256(args.parent),
        "incumbent_sha256": sha256(args.incumbent),
        "base_features_sha256": incumbent.refit_provenance["features_sha256"],
        "base_runtime": info["runtime"],
        "backend": info["backend"],
        "quick_prefill": info["quick_prefill"],
        "feature_names": info["feature_names"],
        "encoder_vector": info["encoder_vector"],
        "supplement_file_sha256": args.supplement_sha256,
        "supplement": provenance,
        "selection_sha256": metadata_hash(expected),
        "excluded_pairs": excluded,
        "role_counts": dict(sorted(selected_counts.items())),
        "group_shortfalls": {
            k: args.groups_per_domain - count for k, count in sorted(selected_counts.items())
        },
        "exclusion_document_sha256": digest_strings(sorted(all_ids)),
        "exclusion_source_sha256": digest_strings(sorted(all_groups)),
    }
    return parent, incumbent, selection, info, rows, names, protocol, members, all_ids, all_groups


def finite(values, size, dtype):
    array = np.asarray(values, dtype=dtype)
    if array.shape != (size,) or not np.isfinite(array).all():
        raise ValueError("Invalid numeric rewrite feature row")
    return array


def collect(args):
    from vibechecker_engine.deep import DeepExtractor
    from vibechecker_engine.text import Refusal

    from .refit_cache import same_numeric_runtime

    parent, _, _, _, _, _, protocol, members, _, _ = inputs(args)
    extractor = DeepExtractor.from_env(include_encoder_evidence=True)
    parent.verify(extractor)
    if (
        extractor.backend != protocol["backend"]
        or extractor.quick.lm.chunk_size != protocol["quick_prefill"]
    ):
        raise ValueError("Rewrite sidecar requires the original Metal/512 extraction profile")
    args.sidecar.parent.mkdir(parents=True, exist_ok=True)
    provenance = {**protocol, "runtime": runtime_identity()}
    if not same_numeric_runtime(protocol["base_runtime"], provenance["runtime"]):
        raise ValueError("Rewrite extractor does not match the audited original numeric runtime")
    with sqlite3.connect(args.sidecar) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK (id=1), provenance TEXT NOT NULL, complete INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS docs (id TEXT PRIMARY KEY, source TEXT NOT NULL, role TEXT NOT NULL, domain TEXT NOT NULL, origin INTEGER NOT NULL, words INTEGER NOT NULL, features BLOB, encoder BLOB, refusal TEXT, CHECK ((features IS NOT NULL AND encoder IS NOT NULL AND refusal IS NULL) OR (features IS NULL AND encoder IS NULL AND refusal IS NOT NULL)))"
        )
        encoded = json.dumps(provenance, sort_keys=True)
        db.execute("INSERT OR IGNORE INTO meta VALUES (1,?,0)", (encoded,))
        if db.execute("SELECT provenance FROM meta WHERE id=1").fetchone() != (encoded,):
            raise ValueError("Sidecar provenance differs from the current selection/runtime")
        have = {r[0] for r in db.execute("SELECT id FROM docs")}
        if not have.issubset(members):
            raise ValueError("Sidecar contains unexpected documents")
        db.commit()
        for key in _progress(
            "Matched rewrite features", sorted(members.keys() - have), len(members) - len(have)
        ):
            group, role, domain, label, doc = members[key]
            x = v = refusal = None
            try:
                raw = extractor.extract(doc.text)
                x = finite(
                    parent.heads.features(raw), len(protocol["feature_names"]), "<f8"
                ).tobytes()
                v = finite(raw.encoder_vector, 769, "<f4").tobytes()
            except Refusal as exc:
                refusal = exc.code
            with db:
                db.execute(
                    "INSERT OR IGNORE INTO docs VALUES (?,?,?,?,?,?,?,?,?)",
                    (key, group, role, domain, label, doc.words, x, v, refusal),
                )
        with db:
            if db.execute("SELECT COUNT(*) FROM docs").fetchone()[0] != len(members):
                raise ValueError("Incomplete sidecar")
            db.execute("UPDATE meta SET complete=1 WHERE id=1")
    return {
        "selected": len(members),
        "resumed": len(have),
        "selection_sha256": protocol["selection_sha256"],
    }


def sidecar_rows(path, protocol, members):
    from .refit_cache import same_numeric_runtime

    result = defaultdict(list)
    pairs = defaultdict(list)
    refusals = Counter()
    domains = {}
    seen = set()
    content = hashlib.sha256()
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("BEGIN")
        record = db.execute("SELECT provenance,complete FROM meta WHERE id=1").fetchone()
        if record is None or record[1] != 1:
            raise ValueError("A completed rewrite sidecar is required")
        recorded = json.loads(record[0])
        if {
            k: v for k, v in recorded.items() if k != "runtime"
        } != protocol or not same_numeric_runtime(
            protocol["base_runtime"], recorded.get("runtime")
        ):
            raise ValueError("Sidecar supplement, sources, heads or extraction scope differs")
        for key, group, role, domain, label, words, x, v, refusal in db.execute(
            "SELECT * FROM docs ORDER BY id"
        ):
            if key not in members or [group, role, domain, label, words] != [
                *members[key][:4],
                members[key][4].words,
            ]:
                raise ValueError("Rewrite sidecar membership differs")
            seen.add(key)
            content.update(key.encode())
            if refusal is not None:
                refusals[f"{role}/{domain}/{refusal}"] += 1
                content.update(refusal.encode())
                continue
            features = finite(np.frombuffer(x, dtype="<f8"), len(protocol["feature_names"]), "<f8")
            encoder = finite(np.frombuffer(v, dtype="<f4"), 769, "<f4")
            content.update(x)
            content.update(v)
            pairs[role, domain, group].append(
                CachedRow(
                    key,
                    group,
                    ROLE_ID[role],
                    label,
                    words,
                    (f"rewrite/{domain}",),
                    features,
                    encoder,
                )
            )
            domains[group] = domain
    if seen != members.keys():
        raise ValueError("Incomplete rewrite sidecar membership")
    for (role, _, _), pair in sorted(pairs.items()):
        if len(pair) == 2 and {r.label for r in pair} == {0, 1}:
            result[ROLE_ID[role]].extend(pair)
    counts = Counter(f"{r.role}/{domains[r.group]}" for values in result.values() for r in values)
    if any(counts[f"{part}/{domain}"] == 0 for part in ROLE_ID.values() for domain in DOMAINS):
        raise ValueError("Both book and news require accepted matched pairs in each role")
    return (
        result,
        domains,
        {
            "matched_documents": dict(sorted(counts.items())),
            "matched_groups": {
                f"{role}/{domain}": counts[f"{part}/{domain}"] // 2
                for role, part in ROLE_ID.items()
                for domain in DOMAINS
            },
            "document_refusals": dict(refusals),
            "content_sha256": content.hexdigest(),
            "runtime": recorded["runtime"],
        },
    )
