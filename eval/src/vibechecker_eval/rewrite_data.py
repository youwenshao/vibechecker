"""Build and authenticate research-only paired RAID rewrites without changing the original cohorts."""

import argparse
import csv
import hashlib
import json
import os
import random
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

import pyarrow.parquet as pq

from .loaders import examples, fingerprint, partition
from .prospective import DATASETS, RelatedGroups, digest, manifest, plan_digest
from .registry import Artifact, fetch, registry, select
from .source_groups import human_source_aliases, source_key

REVISION = "5008b2d167f74bfd4ceff6b3b0512b7097d7cbb1"
SHARDS = {
    "books": ("0003", "be6a92c05534834780bc929c0fb5485fb5249d5ba0d04e6468872dfde17ab8db", 87, 110),
    "news": ("0006", "57d77923b4137057f0b272bc357e012e0a765abdd94da8cb895249713b05158b", 125, 148),
}
CAPS = {"stress": 32, "head": 120, "stack": 64, "calibration": 64}
SCHEME = "raid-paired-rewrite-origin-v1"
RESERVATION = "98e100bdc12a14cefbe35c88f6b48397577e4f11388978c007dbdea6aabaf170"
STACK_PLAN = "b962ca4a703d509e02bc92c6d7fe8ae789a6c25fbed1788591183e7938f69933"
HISTORICAL = "9a8891ffebd90349ecbe07c0c42216b48a14305389e462f21c7e9407d13f3a91"
BASE_ALIASES = "df5312e7d74b4973030b5c7914c25d9f93db4acc3d9de753c45a684dbea4ea8f"
MANIFEST = Path(__file__).with_name("rewrite_manifest.json")
KINDS = ("human", "machine", "clean_human", "clean_machine")


def _role(group):
    split = partition(group)
    if split == "train":
        return "head" if int(fingerprint("head" + group)[:8], 16) % 2 == 0 else "stack"
    return split


def _priority(value):
    return fingerprint(f"{SCHEME}/42/{value}")


@dataclass(frozen=True)
class RewriteDocument:
    id: str
    publisher_id: str
    parent_id: str
    text: str
    generator: str
    words: int

    @property
    def content_sha256(self):
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RewritePair:
    source_group: str
    role: str
    domain: str
    human: RewriteDocument
    machine: RewriteDocument
    clean_human: RewriteDocument
    clean_machine: RewriteDocument


def _payload_digest(rows):
    hasher = hashlib.sha256()
    for pair in sorted(rows, key=lambda row: row.source_group):
        record = asdict(pair)
        for name in KINDS:
            doc = record[name]
            del doc["text"]
            doc["text_sha256"] = getattr(pair, name).content_sha256
        hasher.update(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    return hasher.hexdigest()


def _check_pairs(rows):
    from vibechecker_engine.text import count_words

    docs, groups = set(), set()
    for pair in rows:
        g = pair.source_group
        if (
            not g.startswith("raid:")
            or g in groups
            or pair.domain not in SHARDS
            or pair.role not in CAPS
            or _role(g) != ("stack" if pair.role == "stress" else pair.role)
        ):
            raise ValueError("Unexpected or duplicate rewrite source group")
        groups.add(g)
        for kind in KINDS:
            doc = getattr(pair, kind)
            if (
                doc.id in docs
                or doc.id != fingerprint(doc.text)
                or not 300 <= doc.words <= 2500
                or doc.words != count_words(doc.text)
            ):
                raise ValueError("Corrupt or duplicated projected rewrite document")
            docs.add(doc.id)
        for child, parent in ((pair.human, pair.clean_human), (pair.machine, pair.clean_machine)):
            if (
                child.parent_id != parent.publisher_id
                or parent.parent_id != parent.publisher_id
                or child.generator != parent.generator
            ):
                raise ValueError("Rewrite parent identity mismatch")
        if (
            pair.clean_human.publisher_id != g[5:]
            or pair.human.generator != "human"
            or pair.machine.generator == "human"
        ):
            raise ValueError("Rewrite origin mismatch")


def _read(path, expected):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        meta = json.loads(db.execute("SELECT value FROM provenance").fetchone()[0])
        if meta != expected:
            raise ValueError("Rewrite cohort does not match the pinned provenance manifest")
        rows = []
        for key, entry in db.execute(
            "SELECT source_group,payload FROM pairs ORDER BY source_group"
        ):
            item = json.loads(entry)
            if item["source_group"] != key:
                raise ValueError("Corrupt rewrite source key")
            for name in KINDS:
                item[name] = RewriteDocument(**item[name])
            rows.append(RewritePair(**item))
    _check_pairs(rows)
    if _payload_digest(rows) != expected["selection_sha256"]:
        raise ValueError("Rewrite cohort content differs from the pinned projection")
    return rows


def rewrite_provenance(path):
    expected = json.loads(MANIFEST.read_bytes())
    _read(path, expected)
    return expected


def load_rewrite_pairs(path, *, role, commercial_only=False):
    if commercial_only:
        raise ValueError("The RAID rewrite supplement is research-only")
    if role not in CAPS:
        raise ValueError("Unknown rewrite cohort role")
    return [row for row in _read(path, json.loads(MANIFEST.read_bytes())) if row.role == role]


class _Reservoir:
    """Opaque replica of runner.sample. Exact dedup order and RNG are shared across buckets."""

    def __init__(self, cap):
        self.cap = cap
        self.rng = random.Random(42)
        self.buckets = defaultdict(list)
        self.count = Counter()

    def add(self, row, doc, group):
        key = (row.dataset, row.split, row.label)
        self.count[key] += 1
        bucket = self.buckets[key]
        entry = (doc, group, row.split)
        if len(bucket) < self.cap:
            bucket.append(entry)
        else:
            i = self.rng.randrange(self.count[key])
            if i < self.cap:
                bucket[i] = entry

    def items(self):
        return (row for bucket in self.buckets.values() for row in bucket)


class _Guard:
    def __init__(self):
        self.components = RelatedGroups()
        self.first = {}
        self.ambiguous_documents = set()
        self.roles = defaultdict(set)
        self.human_first = {}
        self.human_conflicts = set()

    def add(self, doc, group, role, label):
        self.roles[group].add(role)
        owner, original_label = self.first.setdefault(doc, (group, label))
        if original_label != label:
            self.ambiguous_documents.add(doc)
        if owner != group:
            self.components.join(owner, group)
        if label == 0:
            prior = self.human_first.setdefault(doc, group)
            if prior != group:
                self.human_conflicts.update((prior, group))


def _original(cache, pinned, guard):
    from vibechecker_engine.text import count_words

    historical, parent = _Reservoir(72), _Reservoir(16)
    quick = (_Reservoir(40), _Reservoir(96))
    deep_seen, quick_seen = set(), set()

    def inventory():
        for row in examples(pinned, cache):
            key = fingerprint(row.text)
            group = source_key(row, document_id=key)
            part = _role(group) if row.split == "train" else row.split
            guard.add(key, group, part, row.label)
            n = count_words(row.text)
            if 300 <= n <= 2500 and key not in deep_seen:
                historical.add(row, key, group)
                parent.add(row, key, group)
                deep_seen.add(key)
            # RAID was first in both Phase 0 Quick draws. Non-RAID groups are
            # excluded from stress below, even if indirectly related to RAID.
            if row.dataset == "raid" and 150 <= n <= 5000 and key not in quick_seen:
                for reservoir in quick:
                    reservoir.add(row, key, group)
                quick_seen.add(key)
            yield row

    aliases = human_source_aliases(inventory())
    if aliases.sha256 != BASE_ALIASES:
        raise ValueError("Pinned corpus alias inventory differs from the original audit")
    final = {
        doc: g
        for doc, g, split in historical.items()
        if split == "test" and int(fingerprint("bakeoff" + g)[:8], 16) % 2 == 1
    }
    if len(final) != 266 or digest(final) != HISTORICAL:
        raise ValueError("Historical final envelope differs from the original audit")
    prior = {
        g
        for res in (parent, *quick)
        for _, g, split in res.items()
        if split in {"train", "calibration"}
    }
    prior.update(g for g in guard.roles if not g.startswith("raid:"))
    return aliases, final, prior


def _stack(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        cfg = json.loads(db.execute("SELECT value FROM meta WHERE key='provenance'").fetchone()[0])
        rows = db.execute(
            "SELECT id, group_id, role, label, words FROM documents ORDER BY id"
        ).fetchall()
    content = hashlib.sha256(
        "".join(f"{k} {g} {p} {y} {n}\n" for k, g, p, y, n in rows).encode()
    ).hexdigest()
    if len(rows) != 2606 or cfg["selection_sha256"] != STACK_PLAN or content != STACK_PLAN:
        raise ValueError("Prior stacker cohort provenance mismatch")
    return {g for k, g, p, y, n in rows}, {k for k, g, p, y, n in rows if p == 2}


def _candidate(doc):
    from vibechecker_engine.text import count_words

    text = doc["generation"]
    words = count_words(text)
    if 300 <= words <= 2500:
        return RewriteDocument(
            fingerprint(text), doc["id"], doc["adv_source_id"], text, doc["model"], words
        )
    return None


def _supplement(cache, guard):
    wanted = defaultdict(lambda: defaultdict(list))
    pub = {}
    for domain, (number, checksum, start, stop) in SHARDS.items():
        url = f"https://huggingface.co/datasets/liamdugan/raid/resolve/{REVISION}/raid/partial-train/{number}.parquet?download=true"
        artifact = Artifact(f"{number}.parquet", url, checksum, "grouped")
        reader = pq.ParquetFile(fetch(artifact, cache))
        pub[domain] = {
            "url": url,
            "sha256": checksum,
            "paraphrase_row_groups_inclusive": [start, stop],
        }
        for ix in range(reader.num_row_groups):
            batch = reader.read_row_group(
                ix,
                columns=[
                    "source_id",
                    "model",
                    "attack",
                    "generation",
                    "domain",
                    "id",
                    "adv_source_id",
                ],
                use_threads=False,
            )
            for r in batch.to_pylist():
                g = "raid:" + r["source_id"]
                key = fingerprint(r["generation"])
                part = _role(g)
                guard.add(key, g, part, int(r["model"] != "human"))
                if (
                    part == "test"
                    or r["domain"] != domain
                    or r["attack"] != "paraphrase"
                    or not start <= ix <= stop
                ):
                    continue
                d = _candidate(r)
                if d is not None:
                    wanted[(domain, g)][r["model"] == "human"].append(d)
    return {k: v for k, v in wanted.items() if True in v and False in v}, pub


def _parents(cache, clean_sha, wanted):
    ids = {
        d.parent_id for by_origin in wanted.values() for docs in by_origin.values() for d in docs
    }
    parents = {}
    with (cache / clean_sha).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["id"] not in ids or row["attack"] != "none":
                continue
            row["adv_source_id"] = row["id"]
            doc = _candidate(row)
            if doc is not None:
                parents[doc.publisher_id] = ("raid:" + row["source_id"], row["domain"], doc)
    return parents


def _choose(wanted, parents, guard, final, reservation, prior_fit, stack_groups, validation_docs):
    from vibechecker_engine.text import Refusal, prepare, validate

    roots = guard.components.root
    component_roles = defaultdict(set)
    for g, roles in guard.roles.items():
        component_roles[roots(g)].update(roles)
    conflict = {r for r, roles in component_roles.items() if len(roles) != 1 or "test" in roles}
    # A new pair may be used inside a source-hashed head-development fold together
    # with legacy examples. Reject sibling IDs even when both are in the same outer role.
    component_sizes = Counter(roots(g) for g in guard.roles)
    conflict.update(g for g, size in component_sizes.items() if size > 1)
    conflict.update(map(roots, guard.human_conflicts))
    forbidden_docs = (
        set(final)
        | validation_docs
        | guard.ambiguous_documents
        | {doc for doc, _ in reservation["members"]}
    )
    reserved_groups = {g for _, g in reservation["members"]}
    prior_stress = set()
    historical_groups = set(final.values())
    for g, roles in guard.roles.items():
        if fingerprint(g) in reserved_groups or g in historical_groups:
            conflict.add(roots(g))
        if g in prior_fit or fingerprint(g) in stack_groups or "head" in roles:
            prior_stress.add(roots(g))
    admitted = {}

    def english(doc):
        if doc.id not in admitted:
            try:
                validate(prepare(doc.text), "deep")
            except Refusal:
                admitted[doc.id] = False
            else:
                admitted[doc.id] = True
        return admitted[doc.id]

    pairs, used_roots, used_docs = [], set(), set()
    for domain in SHARDS:
        for role, cap in CAPS.items():
            n = 0
            groups = sorted(
                (g for d, g in wanted if d == domain), key=lambda g: _priority(role + "/" + g)
            )
            for g in groups:
                root = roots(g)
                if (
                    root in conflict
                    or root in used_roots
                    or _role(g) != ("stack" if role == "stress" else role)
                ):
                    continue
                if role == "stress" and root in prior_stress:
                    continue
                by_origin = wanted[domain, g]
                selected = []
                local = set()
                for human in (True, False):
                    for d in sorted(by_origin[human], key=lambda d: _priority(d.id)):
                        p = parents.get(d.parent_id)
                        if p is None or p[:2] != (g, domain) or p[2].generator != d.generator:
                            continue
                        original = p[2]
                        if human and original.publisher_id != g[5:]:
                            continue
                        ids = {d.id, original.id}
                        if len(ids) != 2 or ids & (local | forbidden_docs | used_docs):
                            continue
                        if not english(d) or not english(original):
                            continue
                        selected += [d, original]
                        local.update(ids)
                        break
                    else:
                        break
                if len(selected) == 4:
                    h, hp, m, mp = selected
                    pairs.append(RewritePair(g, role, domain, h, m, hp, mp))
                    used_docs.update(local)
                    used_roots.add(root)
                    n += 1
                    if n == cap:
                        break
    held_out = {roots(g) for g, roles in guard.roles.items() if "test" in roles}
    selected_docs = {getattr(p, kind).id for p in pairs for kind in KINDS}
    selected_components = {roots(p.source_group) for p in pairs}
    stress_components = {roots(p.source_group) for p in pairs if p.role == "stress"}
    isolation = {
        "selected_components": len(selected_components),
        "non_singleton_selected_components": sum(
            component_sizes[r] != 1 for r in selected_components
        ),
        "historical_document_overlap": len(selected_docs & final.keys()),
        "prospective_document_overlap": len(
            selected_docs & {doc for doc, _ in reservation["members"]}
        ),
        "reserved_validation_document_overlap": len(selected_docs & validation_docs),
        "conflicting_label_document_overlap": len(selected_docs & guard.ambiguous_documents),
        "input_hashes_with_both_origin_labels": len(guard.ambiguous_documents),
        "held_out_component_overlap": len(selected_components & held_out),
        "stress_prior_fit_component_overlap": len(stress_components & prior_stress),
        "selected_human_alias_groups": len({p.source_group for p in pairs} & guard.human_conflicts),
        "complete_input_components_with_multiple_source_ids": sum(
            n > 1 for n in component_sizes.values()
        ),
        "distinct_input_document_hashes": len(guard.first),
        "distinct_input_source_ids": len(guard.roles),
    }
    if any(v for k, v in isolation.items() if k.endswith("_overlap")):
        raise ValueError("Rewrite cohort intersects a reserved source or document")
    if isolation["non_singleton_selected_components"] or isolation["selected_human_alias_groups"]:
        raise ValueError("A rewrite source shares a normalized passage with another source")
    return pairs, isolation


def _write(path, rows, metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix=".rewrite-", delete=False) as f:
        temporary = Path(f.name)
    try:
        with closing(sqlite3.connect(temporary)) as db, db:
            db.execute("CREATE TABLE provenance(value TEXT NOT NULL)")
            db.execute("INSERT INTO provenance VALUES (?)", (json.dumps(metadata, sort_keys=True),))
            db.execute("CREATE TABLE pairs(source_group TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.executemany(
                "INSERT INTO pairs VALUES (?,?)",
                ((r.source_group, json.dumps(asdict(r), ensure_ascii=False)) for r in rows),
            )
        _read(temporary, metadata)
        try:
            os.link(temporary, path)
        except FileExistsError:
            # Reuse an authenticated identical projection. An unrelated existing file
            # or concurrently published different cohort must never be overwritten.
            _read(path, metadata)
    finally:
        temporary.unlink(missing_ok=True)


def build(
    cache, stack_db, reservation_path, output, *, record_manifest=None, commercial_only=False
):
    if commercial_only:
        raise ValueError("The RAID rewrite supplement is research-only")
    if record_manifest and record_manifest.resolve() in {
        output.resolve(),
        stack_db.resolve(),
        reservation_path.resolve(),
    }:
        raise ValueError("The manifest output must be separate from cohort inputs and outputs")
    pinned = select(registry(), DATASETS)
    reserved = json.loads(reservation_path.read_bytes())
    if plan_digest(reserved) != RESERVATION or reserved["input_manifest"] != manifest(pinned):
        raise ValueError("Pinned prospective membership manifest mismatch")
    stack_groups, validation_docs = _stack(stack_db)
    guard = _Guard()
    aliases, final, prior = _original(cache, pinned, guard)
    before = set(guard.human_conflicts)
    # The auxiliary human controls also draw from PERSUADE. Protect its complete
    # input with hashes; its rows never enter the supplemental training cohort.
    control_sources = select(registry(), ["persuade"])
    for row in examples(control_sources, cache):
        key = fingerprint(row.text)
        guard.add(key, source_key(row, document_id=key), "external-control", row.label)
    wanted, pub = _supplement(cache, guard)
    parents = _parents(cache, pinned[0].artifacts[0].sha256, wanted)
    rows, isolation = _choose(
        wanted, parents, guard, final, reserved, prior, stack_groups, validation_docs
    )
    _check_pairs(rows)
    root = guard.components.root
    if len({root(r.source_group) for r in rows}) != len(rows):
        raise ValueError("A selected source component was reused")
    metadata = {
        "scheme": SCHEME,
        "commercial_ok": False,
        "upstream": "liamdugan/raid",
        "revision": REVISION,
        "word_bounds": [300, 2500],
        "language": "English; production Deep admission on all four documents",
        "selection_method": (
            "Seed 42. Only singleton source components from the original five datasets, "
            "PERSUADE control corpus and both new shards. "
            "One human rewrite, one machine rewrite and both exact clean parents per source. "
            "Stress draws first from stack-training sources absent from prior fits."
        ),
        "role_caps_per_domain": CAPS,
        "input_manifest": manifest(pinned),
        "control_corpora_for_hash_exclusion": manifest(control_sources),
        "supplement_shards": pub,
        "original_source_aliases": aliases.summary(),
        "combined_human_alias_group_count": len(guard.human_conflicts),
        "new_human_alias_group_hashes": sorted(
            fingerprint(g) for g in guard.human_conflicts - before
        ),
        "historical_envelope_documents": len(final),
        "historical_envelope_sha256": digest(final),
        "prospective_reservation_sha256": RESERVATION,
        "prior_refit_plan_sha256": STACK_PLAN,
        "selection_sha256": _payload_digest(rows),
        "pair_count": len(rows),
        "document_count": 4 * len(rows),
        "document_identity": (
            "Each .id is SHA-256 of casefolded, whitespace-collapsed UTF-8 text. "
            "The full projection binds each document's exact UTF-8 SHA-256, publisher/parent IDs, "
            "word count, generator, group, role and domain."
        ),
        "machine_generators_by_role": {
            role: dict(sorted(Counter(r.machine.generator for r in rows if r.role == role).items()))
            for role in CAPS
        },
        "support": {
            dom: {role: sum(r.domain == dom and r.role == role for r in rows) for role in CAPS}
            for dom in SHARDS
        },
        "role_groups_sha256": {
            role: digest(fingerprint(r.source_group) for r in rows if r.role == role)
            for role in CAPS
        },
        "isolation": isolation,
    }
    if MANIFEST.is_file() and metadata != json.loads(MANIFEST.read_bytes()):
        raise ValueError("Regenerated rewrite projection differs from the checked-in manifest")
    if record_manifest is None and not MANIFEST.is_file():
        raise ValueError("Missing pinned rewrite manifest")
    _write(output, rows, metadata)
    if record_manifest is not None:
        record_manifest.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cache", "stack-db", "reservation", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--record-manifest", type=Path)
    parser.add_argument("--commercial-only", action="store_true")
    args = parser.parse_args()
    result = build(
        args.cache,
        args.stack_db,
        args.reservation,
        args.output,
        record_manifest=args.record_manifest,
        commercial_only=args.commercial_only,
    )
    print(json.dumps({"pairs": result["support"], "selection_sha256": result["selection_sha256"]}))


if __name__ == "__main__":
    main()
