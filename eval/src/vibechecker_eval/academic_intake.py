"""Read signed academic-source projections, match human controls and freeze membership without scores."""

import gzip
import hashlib
import json
import sqlite3
from collections import Counter

import numpy as np
from scipy.optimize import linear_sum_assignment

from .deep_cohort import fold
from .loaders import Example, fingerprint, partition
from .refit_cache import digest_strings
from .registry import sha256
from .rewrite_sidecar import metadata_hash

FIT_ROLES = ("stack", "calibration")
HUMAN_DEV = "external_human_development"
SEED = 42
MACHINE_SCHEME = "raid-academic-machine-paraphrase-candidates-v1"
ISOLATION = {
    "academic_dev",
    "across_roles_source",
    "any_reserved_or_training_document",
    "current_head",
    "historical",
    "human_controls",
    "nonsingleton_or_conflicting_component",
    "original_or_quick",
    "original_stack",
    "paired_rewrite",
    "prospective",
}
ARTIFACTS = {
    "machine_projection",
    "machine_manifest",
    "human_projection",
    "human_manifest",
    "subjects",
    "v1_parent",
    "v2_incumbent",
    "v2_selection",
    "v3_selection",
    "probe",
    "base_features",
    "rewrite_sidecar",
    "rewrite_supplement",
    "band_controls",
    "academic_plan",
    "academic_features",
    "academic_binding",
    "encoder_original",
    "encoder_expanded",
}


def study_paths(study_path, expected_sha):
    if sha256(study_path) != expected_sha:
        raise ValueError("Study specification differs from the operator's frozen SHA")
    study = json.loads(study_path.read_bytes())
    if study["scheme"] != "academic-origin-additive-v1" or set(study["files"]) != ARTIFACTS:
        raise ValueError("A complete academic study artifact map is required")
    paths = {}
    for name, record in study["files"].items():
        path = (study_path.parent / record["path"]).resolve()
        if sha256(path) != record["sha256"]:
            raise ValueError("Study artifact digest differs: " + name)
        paths[name] = path
    return paths


def verified_doc(d, *, check_gate):
    from vibechecker_engine.text import count_words, prepare, validate

    text = d["text"]
    if (
        d["id"] != fingerprint(text)
        or d["text_sha256"] != hashlib.sha256(text.encode()).hexdigest()
        or d["words"] != count_words(text)
        or not d["publisher_id"]
    ):
        raise ValueError("Publisher document/hash/length does not verify")
    if check_gate:
        validate(prepare(text), "deep")


def projection(paths, side):
    manifest = json.loads(paths[side + "_manifest"].read_bytes())
    data = paths[side + "_projection"]
    if manifest["gzip_sha256"] != sha256(data):
        raise ValueError("Signed projection bytes differ")
    with gzip.open(data, "rb") as f:
        payload = f.read()
    if manifest["raw_content_sha256"] != hashlib.sha256(payload).hexdigest():
        raise ValueError("Signed decompressed source identity differs")
    return manifest, [json.loads(line) for line in payload.splitlines()]


def verify_machine(manifest, rows):
    if (
        manifest["scheme"] != MACHINE_SCHEME
        or set(manifest["isolation"]) != ISOLATION
        or any(v != 0 for v in manifest["isolation"].values())
    ):
        raise ValueError("Positive RAID projection lacks complete source-isolation proof")
    recorded = {}
    for r in rows:
        child, clean, human = r["child"], r["clean_machine"], r["clean_human"]
        for d in (child, clean, human):
            verified_doc(d, check_gate=d is child)
        g = r["source_group"]
        part = partition(g)
        item = Example("", 1, "raid-attacks", part, "other", source_group=g)
        role = "stack" if part == "train" and fold(item, "head") == 1 else part
        if (
            r["role"] not in FIT_ROLES
            or r["role"] != role
            or not g.startswith("raid:")
            or r["group"] != fingerprint(g)
            or r["domain"] != "abstracts"
            or r["target_label"] != 1
            or child["publisher_parent"] != clean["publisher_id"]
            or child["generator"] != clean["generator"]
            or child["generator"] == "human"
            or human["generator"] != "human"
            or child["id"] in recorded
        ):
            raise ValueError("RAID target or publisher source linkage differs")
        recorded[child["id"]] = {
            "group": r["group"],
            "id": child["id"],
            "role": role,
            "target_label": 1,
            "generator": child["generator"],
            "words": child["words"],
            "clean_human": human["id"],
            "clean_machine": clean["id"],
        }
    if len({r["group"] for r in rows}) != len(rows) or sorted(
        recorded.values(), key=lambda r: r["id"]
    ) != sorted(manifest["members"], key=lambda r: r["id"]):
        raise ValueError("RAID rows differ from the original source commitment")


def match_role(machines, humans, seed=SEED):
    """Maximum-cardinality 1:1 common-field matching, then minimum total log length distance."""
    from math import log

    if not machines or not humans:
        return []
    ordered = lambda rows: sorted(
        rows, key=lambda r: fingerprint(f"academic-match/{seed}/" + r["id"])
    )
    machines, humans = ordered(machines), ordered(humans)
    costs = np.full((len(machines), len(humans)), len(machines) + len(humans) + 1.0, dtype=float)
    for i, left in enumerate(machines):
        for j, right in enumerate(humans):
            ratio = max(left["words"], right["words"]) / min(left["words"], right["words"])
            if (
                left["subject"]
                and left["subject"] == right["subject"]
                and ratio <= 1.25
                and (
                    not right.get("matched_machine_group")
                    or right["matched_machine_group"] == left.get("group")
                )
            ):
                costs[i, j] = abs(log(ratio))
    ix, jx = linear_sum_assignment(costs)
    return [(machines[i], humans[j]) for i, j in zip(ix, jx, strict=True) if costs[i, j] < 1]


def member(r, label, subject, subject_year=None):
    child = r["child"]
    return {
        "id": child["id"],
        "group": r["group"],
        "role": r["role"],
        "label": label,
        "source": r.get("source", "RAID"),
        "domain": r["domain"],
        "subject": subject,
        "year": subject_year if label else r.get("year"),
        "matched_machine_group": r.get("matched_machine_group"),
        "parent_ids": [r["clean_machine"]["id"], r["clean_human"]["id"]] if label else [],
        "kind": "native_human" if not label else "machine_paraphrase",
        "generator": child["generator"],
        "words": child["words"],
        "text": child["text"],
    }


def protected_keys(paths):
    ids, groups = set(), set()

    def sqlite(name, query):
        with sqlite3.connect(paths[name].as_uri() + "?mode=ro", uri=True) as db:
            return list(db.execute(query))

    for name, query in (
        ("base_features", "SELECT id,group_id FROM documents"),
        ("band_controls", "SELECT id,grp FROM controls"),
    ):
        for key, group in sqlite(name, query):
            ids.add(key)
            groups.add(group)
    for name in ("encoder_original", "encoder_expanded"):
        ids.update(r[0] for r in sqlite(name, "SELECT digest FROM vectors"))
    for r in json.loads(paths["academic_plan"].read_bytes())["members"]:
        ids.add(r["id"])
        groups.add(r["group"])
    for g, *docids in sqlite(
        "rewrite_supplement",
        "SELECT source_group,"
        "json_extract(payload,'$.human.id'), json_extract(payload,'$.machine.id'),"
        "json_extract(payload,'$.clean_human.id'),json_extract(payload,'$.clean_machine.id') FROM pairs",
    ):
        ids.update(docids)
        groups.add(fingerprint(g))
    return ids, groups


def project(paths):
    machine_manifest, machine = projection(paths, "machine")
    human_manifest, human = projection(paths, "human")
    verify_machine(machine_manifest, machine)
    subjects = json.loads(paths["subjects"].read_bytes())
    if subjects["machine_projection_sha256"] != sha256(paths["machine_projection"]):
        raise ValueError(
            "Scientific subject evidence must bind the exact machine source projection"
        )
    map_by_group = subjects["groups"]
    if human_manifest.get("scheme") != "pre2020-academic-human-reference-v1" or any(
        human_manifest["isolation"].get(k) != 0 for k in ISOLATION
    ):
        raise ValueError("Human reference projection lacks authenticated source/family isolation")
    old_ids, old_groups = protected_keys(paths)
    docs, groups = set(), set()
    pool = []
    for label, source in ((1, machine), (0, human)):
        for r in source:
            child = r["child"]
            if not label:
                verified_doc(child, check_gate=True)
                if (
                    r["role"] not in (*FIT_ROLES, HUMAN_DEV)
                    or r["target_label"] != 0
                    or r["transformation"] != "native"
                    or child["generator"] != "human"
                    or not 0 < int(r["year"]) < 2020
                    or not r["source"]
                    or not r["license"]
                    or r["group"] != fingerprint(r["source_group"])
                ):
                    raise ValueError("Invalid native-human role, source, date or license")
            ancestors = {r["clean_human"]["id"], r["clean_machine"]["id"]} if label else set()
            identities = ancestors | {child["id"]}
            if identities & (old_ids | docs) or r["group"] in old_groups | groups:
                raise ValueError("Source, clean-parent or document overlap in academic projection")
            docs.update(identities)
            groups.add(r["group"])
            if label:
                subject_record = map_by_group.get(r["group"], {})
                subject = subject_record.get("subject") if subject_record.get("evidence") else None
            else:
                subject = r.get("subject")
            pool.append(member(r, label, subject, subject_record.get("year") if label else None))
    kept = []
    links, paired_hashes = {}, {}
    for role in FIT_ROLES:
        left = [r for r in pool if r["role"] == role and r["label"]]
        right = [r for r in pool if r["role"] == role and not r["label"]]
        pairs = match_role(left, right)
        links[role] = len(pairs)
        paired_hashes[role] = digest_strings(sorted(a["id"] + " " + b["id"] for a, b in pairs))
        for left, right in pairs:
            kept.extend((left, right))
    dev = [r for r in pool if r["role"] == HUMAN_DEV]
    kept.extend(dev)
    fit_subject = {r["subject"] for r in kept if r["role"] in FIT_ROLES}
    shared_dev = sum(r["subject"] in fit_subject for r in dev)
    counts = lambda values: dict(
        sorted(
            Counter(
                f"{r['role']}/{r['source']}/{r['subject'] or 'unknown'}/{r['kind']}" for r in values
            ).items()
        )
    )
    kept.sort(key=lambda r: r["id"])
    summary = {
        "scheme": "academic-origin-additive-membership-v1",
        "seed": SEED,
        "selection_rule": "Same declared scientific field; maximum-cardinality 1:1 groups by role at <=1.25 length ratio, then minimum absolute log length distance.",
        "sources": {
            name: sha256(paths[name])
            for name in (
                "machine_manifest",
                "human_manifest",
                "subjects",
                "machine_projection",
                "human_projection",
            )
        },
        "available": counts(pool),
        "accepted": counts(kept),
        "fit_pairs": links,
        "matched_document_pairs_sha256": paired_hashes,
        "independent_human_development": len(dev),
        "independent_humans_in_fit_subject": shared_dev,
        "source_document_overlap": 0,
        "source_group_overlap": 0,
        "ready": all(links.values()) and shared_dev > 0,
        "selection_sha256": metadata_hash(
            [{k: v for k, v in r.items() if k != "text"} for r in kept]
        ),
        "source_order_sha256": digest_strings(r["group"] for r in kept),
    }
    return kept, summary
