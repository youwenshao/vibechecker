"""Reserve a second, score-blind final cohort outside all historical development and test sources."""

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from .deep_cohort import fold
from .loaders import examples, fingerprint
from .metrics import length_bin
from .registry import registry, select
from .runner import sample
from .source_groups import human_source_aliases, source_key

SCHEME = "prospective-final-group-audit-v1"
DATASETS = ("raid", "raid-attacks", "asap", "ellipse", "liang")
TARGET = 512


def digest(values):
    return fingerprint(" ".join(sorted(values)))


def plan_digest(plan):
    return hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def manifest(datasets):
    return {
        d.id: {"version": d.version, "sha256": [a.sha256 for a in d.artifacts]} for d in datasets
    }


@dataclass(frozen=True)
class Candidate:
    document: str
    group: str
    dataset: str
    generator: str
    attack: str
    length: str
    genre: str
    writer: str


class RelatedGroups:
    """Join source IDs whenever the corpus contains the same normalized text under both."""

    def __init__(self):
        self.parent = {}

    def root(self, group):
        while group in self.parent:
            parent = self.parent[group]
            self.parent[group] = self.parent.get(parent, parent)
            group = parent
        return group

    def join(self, a, b):
        a, b = sorted((self.root(a), self.root(b)))
        if a != b:
            self.parent[b] = a


def support(rows, components):
    counts = Counter()
    for row in rows:
        for name in ("dataset", "generator", "attack", "length", "genre", "writer"):
            counts[f"{name}/{getattr(row, name)}"] += 1
    return {
        "documents": len(rows),
        "source_groups": len({r.group for r in rows}),
        "source_components": len({components.root(r.group) for r in rows}),
        "strata": dict(sorted(counts.items())),
    }


def reserve_balanced(pool, components, target):
    # Each source gets one turn, rotating through its generator/attack/length cells.
    # Group priority uses the frozen scheme and source hash, independent of model output.
    by_source = defaultdict(lambda: defaultdict(list))
    priority = {}
    for row in pool:
        root = components.root(row.group)
        if root not in priority:
            priority[root] = fingerprint(f"{SCHEME}/group/{root}")
        by_source[row.dataset][row.generator, row.attack, row.length].append(
            (priority[root], row.document, row)
        )
    queue = deque()
    for source, cells in sorted(by_source.items()):
        cell_order = sorted(cells, key=lambda key: fingerprint(f"{SCHEME}/cell/{source}/{key}"))
        queue.append(deque(deque(sorted(cells[key])) for key in cell_order))
    selected, used = [], set()
    while queue and len(selected) < target:
        cells = queue.popleft()
        while cells:
            cell = cells.popleft()
            while cell and components.root(cell[0][2].group) in used:
                cell.popleft()
            if cell:
                row = cell.popleft()[2]
                used.add(components.root(row.group))
                selected.append(row)
                if cell:
                    cells.append(cell)
                break
        if cells:
            queue.append(cells)
    return selected


def reserve(stream, count_words, audit, datasets, *, target=TARGET):
    pinned = manifest(datasets)
    if pinned != audit["input_manifest"] or list(pinned) != list(audit["input_manifest"]):
        raise ValueError(
            "Historical envelope requires its original pinned dataset manifest and order"
        )
    history, _ = sample(stream(), 72, 42, count_words, length_range=(300, 2500))
    historical = {
        fingerprint(r.text): source_key(r)
        for r, _ in history
        if r.split == "test" and fold(r, "bakeoff") == 1
    }
    expected = audit["after"]["final_envelope"]
    if (
        len(historical) != expected["documents"]
        or len(set(historical.values())) != expected["source_groups"]
        or digest(historical) != expected["document_id_sha256"]
    ):
        raise ValueError(
            "Reconstructed historical candidate envelope differs from its independent audit"
        )
    historical_groups = set(historical.values())
    protected = set(historical_groups)
    components = RelatedGroups()
    first_group, candidates = {}, {}
    multi_source_docs = set()

    def inspect():
        for r in stream():
            key = fingerprint(r.text)
            group = source_key(r, document_id=key)
            prior = first_group.setdefault(key, group)
            if prior != group:
                components.join(prior, group)
                multi_source_docs.add(key)
            if r.split != "test" or fold(r, "bakeoff") != 1:
                protected.add(group)
            elif key not in candidates and group not in historical_groups:
                words = count_words(r.text)
                if 300 <= words <= 2500:
                    candidates[key] = Candidate(
                        key,
                        group,
                        r.dataset,
                        r.generator,
                        r.attack,
                        length_bin(words),
                        r.genre,
                        r.writer,
                    )
            yield r

    aliases = human_source_aliases(inspect())
    protected.update(aliases.groups)
    blocked = {components.root(group) for group in protected}
    pool = [
        r
        for r in candidates.values()
        if r.document not in multi_source_docs and components.root(r.group) not in blocked
    ]
    selected = reserve_balanced(pool, components, target)
    if not selected:
        raise ValueError("No independent prospective audit groups remain")
    roots = {components.root(r.group) for r in selected}
    groups = {r.group for r in selected}
    ids = {r.document for r in selected}
    isolation = {
        "protected_source_groups": len(protected),
        "protected_components": len(blocked),
        "protected_component_overlap": len(roots & blocked),
        "historical_document_overlap": len(ids & historical.keys()),
        "historical_source_overlap": len(groups & historical_groups),
        "human_alias_overlap": len(groups & aliases.groups),
    }
    if len(selected) != len(roots) or any(
        v for k, v in isolation.items() if k.endswith("_overlap")
    ):
        raise ValueError("Audit isolation check failed")
    members = sorted([r.document, fingerprint(r.group)] for r in selected)
    return {
        "scheme": SCHEME,
        "target": target,
        "input_manifest": pinned,
        "dataset_order": list(pinned),
        "historical_envelope": expected,
        "source_aliases": aliases.summary(),
        "selection_method": "One normalized document per connected source component; rotate among datasets and generator/attack/length cells by fixed source hash. All splits and lengths participate in the duplicate-text quarantine. Before language screening.",
        "protected_group_ids_sha256": digest(fingerprint(g) for g in protected),
        "pool": support(pool, components),
        "selection": support(selected, components),
        "isolation": isolation,
        "member_ids_sha256": digest(ids),
        "members": members,
    }


def resolve(plan, expected_digest, datasets, stream, count_words):
    if (
        plan_digest(plan) != expected_digest
        or plan["scheme"] != SCHEME
        or plan["input_manifest"] != manifest(datasets)
        or plan["dataset_order"] != [d.id for d in datasets]
    ):
        raise ValueError("Prospective audit plan digest, scheme or pinned manifest differs")
    wanted = dict(plan["members"])
    if (
        len(wanted) != len(plan["members"])
        or len(wanted) != plan["selection"]["documents"]
        or len(set(wanted.values())) != len(wanted)
        or digest(wanted) != plan["member_ids_sha256"]
    ):
        raise ValueError("Invalid frozen audit membership")
    seen = {}
    for r in stream:
        key = fingerprint(r.text)
        if key not in wanted:
            continue
        if (
            r.split != "test"
            or fold(r, "bakeoff") != 1
            or fingerprint(source_key(r, document_id=key)) != wanted[key]
        ):
            raise ValueError("Frozen audit member has a different source or split")
        if key not in seen:
            n = count_words(r.text)
            if not 300 <= n <= 2500:
                raise ValueError("Frozen audit member has a different length")
            seen[key] = (r, n)
    if seen.keys() != wanted.keys():
        raise ValueError("Missing prospective audit members")
    return [seen[key] for key in sorted(seen)]


def publish(plan, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf8") as out:
        temp = Path(out.name)
    try:
        temp.write_text(json.dumps(plan, indent=2, allow_nan=False) + "\n", encoding="utf8")
        try:
            os.link(temp, path)
        except FileExistsError:
            if json.loads(path.read_bytes()) != plan:
                raise ValueError("A different plan already occupies this path") from None
    finally:
        temp.unlink(missing_ok=True)


def main(argv=None):
    from vibechecker_engine.text import count_words

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("eval/.cache"))
    parser.add_argument(
        "--historical-audit",
        type=Path,
        default=Path("eval/reports/phase-1/expanded-source-membership.json"),
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    datasets = select(registry(), DATASETS)
    plan = reserve(
        lambda: examples(datasets, args.cache),
        count_words,
        json.loads(args.historical_audit.read_bytes()),
        datasets,
    )
    publish(plan, args.out)
    print(
        json.dumps(
            {
                "plan_sha256": plan_digest(plan),
                "pool": plan["pool"]["documents"],
                "reserved": plan["selection"]["documents"],
                "isolation": plan["isolation"],
            }
        )
    )


if __name__ == "__main__":
    main()
