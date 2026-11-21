"""Reconstruct an already frozen academic development sample from its published commitments."""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict, deque
from itertools import combinations
from pathlib import Path

import pyarrow.dataset as ds
from pyarrow import csv

from .deep_cohort import fold
from .deep_runner import write_json
from .loaders import Example, fingerprint, partition
from .refit_cache import VALIDATION, digest_strings
from .registry import registry, sha256


def commitment(items):
    return fingerprint(" ".join(sorted(items)))


def priority(value):
    return fingerprint("aux-raid-paraphrase-v1/42/" + value)


def retained_groups(groups, report):
    """Match the signed original set using opaque development group IDs alone."""
    count = report["rewritten_prompt_groups"]
    extra = len(groups) - count
    if not 0 <= extra <= 3:
        raise ValueError(
            f"Cannot reconstruct the published development group set ({len(groups)} eligible; expected {count})"
        )
    for excluded in combinations(sorted(groups), extra):
        keep = groups.difference(excluded)
        if commitment(keep) == report["rewritten_group_sha256"]:
            return keep
    raise ValueError("Development groups differ from the published commitment")


def eligible(text):
    from vibechecker_engine.text import Refusal, count_words, prepare, validate

    if not 300 <= count_words(text) <= 2500:
        return False
    try:
        validate(prepare(text), "deep")
        return True
    except Refusal:
        return False


def round_robin(rows, keep):
    queues = {
        gen: deque(sorted(set(pairs), key=lambda row: priority(row[1])))
        for gen, pairs in sorted(rows.items(), key=lambda item: priority(item[0]))
    }
    chosen = {}
    while len(chosen) < len(keep):
        before = len(chosen)
        for gen, queue in queues.items():
            while queue:
                group, doc = queue.popleft()
                if group not in chosen and group in keep:
                    chosen[group] = (gen, doc)
                    break
        if before == len(chosen):
            break
    return chosen


def resolve(report, cache, base_features):
    """Return verified passages in memory only; membership is never selected on a model score."""
    if report["version"] != "aux-raid-paraphrase-v1" or report["seed"] != 42:
        raise ValueError("Unsupported development registration")
    catalog = registry()
    clean, attacks = (catalog[k].artifacts[0] for k in ("raid", "raid-attacks"))
    for k, item in (("raid", clean), ("raid-attacks", attacks)):
        if (
            report["pinned_datasets"][k]["sha256"] != [item.sha256]
            or sha256(cache / item.sha256) != item.sha256
        ):
            raise ValueError("Publisher source differs from the prior development registration")
    with sqlite3.connect(base_features.resolve().as_uri() + "?mode=ro", uri=True) as db:
        reserved = dict(db.execute("SELECT id,group_id FROM documents WHERE role=?", (VALIDATION,)))
    if (
        len(reserved) != report["reserved_validation_docs"]
        or commitment(reserved) != report["reserved_validation_doc_sha256"]
    ):
        raise ValueError("Original validation envelope cannot be reproduced")
    occupied = set(reserved.values())
    data = ds.dataset(cache / attacks.sha256, format="parquet")
    machine_rewrite = (ds.field("attack") == "paraphrase") & (ds.field("model") != "human")
    sources = (
        data.to_table(columns=["source_id"], filter=machine_rewrite).column(0).unique().to_pylist()
    )
    authorized = []
    for source in sources:
        raw = "raid:" + source
        dummy = Example("", 1, "raid-attacks", partition(raw), "other", source_group=raw)
        if (
            dummy.split == "test"
            and fold(dummy, "bakeoff") == 0
            and fingerprint(raw) not in occupied
        ):
            authorized.append(source)
    possible, records = defaultdict(list), {}
    for batch in data.scanner(
        columns=["source_id", "model", "generation", "adv_source_id", "domain"],
        filter=ds.field("source_id").isin(authorized) & machine_rewrite,
    ).to_batches():
        for row in batch.to_pylist():
            group = "raid:" + row["source_id"]
            key = fingerprint(row["generation"])
            if key not in reserved and eligible(row["generation"]):
                possible[row["model"]].append((group, key))
                records[(group, key)] = row
    keep = retained_groups({g for pairs in possible.values() for g, _ in pairs}, report)
    chosen = round_robin(possible, keep)
    if commitment(k for gen, k in chosen.values()) != report["rewritten_document_sha256"]:
        raise ValueError("Development document membership differs from published commitment")
    clean_data = ds.dataset(
        cache / clean.sha256,
        format=ds.CsvFileFormat(
            parse_options=csv.ParseOptions(newlines_in_values=True),
            read_options=csv.ReadOptions(block_size=2**24),
        ),
    )
    supports = defaultdict(list)
    for batch in clean_data.scanner(
        columns=["id", "source_id", "model", "generation", "domain"],
        filter=ds.field("source_id").isin([g.removeprefix("raid:") for g in keep])
        & (ds.field("attack") == "none"),
    ).to_batches():
        for row in batch.to_pylist():
            group = "raid:" + row["source_id"]
            gen, _ = chosen[group]
            if (
                row["model"] in (gen, "human")
                and fingerprint(row["generation"]) not in reserved
                and eligible(row["generation"])
            ):
                supports[group, row["model"]].append(row)
    rows = []
    for group, (gen, key) in chosen.items():
        rewrite = records[group, key]

        def entry(kind, doc, group=group):
            return {
                "id": fingerprint(doc["generation"]),
                "group": fingerprint(group),
                "role": "frozen-independent-development",
                "kind": kind,
                "generator": doc["model"],
                "domain": doc["domain"],
                "text": doc["generation"],
            }

        rows.append(entry("rewrite", rewrite))
        candidates = sorted(
            supports[group, gen], key=lambda d: priority(fingerprint(d["generation"]))
        )
        original = [r for r in candidates if r["id"] == rewrite["adv_source_id"]]
        if original:
            rows.append(entry("original_clean", original[0]))
        elif candidates:
            rows.append(entry("same_prompt_clean", candidates[0]))
        humans = sorted(
            supports[group, "human"], key=lambda d: priority(fingerprint(d["generation"]))
        )
        if humans:
            rows.append(entry("same_prompt_human", humans[0]))
    if (
        len({r["id"] for r in rows}) != len(rows)
        or dict(Counter(r["kind"] for r in rows)) != report["selected_kinds"]
        or commitment(r["id"] for r in rows) != report["scored_document_sha256"]
    ):
        raise ValueError("Reconstructed controls differ from published development membership")
    return sorted(rows, key=lambda x: x["id"])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("prior-report", "cache", "base-features", "plan-out", "summary-out"):
        p.add_argument("--" + key, type=Path, required=True)
    args = p.parse_args(argv)
    report = json.loads(args.prior_report.read_bytes())
    rows = resolve(report, args.cache, args.base_features)
    membership = [{k: v for k, v in r.items() if k != "text"} for r in rows]
    result = {
        "scheme": "reconstructed-academic-development-v1",
        "prior_report_sha256": sha256(args.prior_report),
        "documents": len(rows),
        "groups": len({r["group"] for r in rows}),
        "kinds": dict(Counter(r["kind"] for r in rows)),
        "domains": dict(Counter(r["domain"] for r in rows)),
        "rewrite_generator_counts": dict(
            sorted(Counter(r["generator"] for r in rows if r["kind"] == "rewrite").items())
        ),
        "rewritten_document_sha256": report["rewritten_document_sha256"],
        "rewritten_group_sha256": report["rewritten_group_sha256"],
        "scored_document_sha256": report["scored_document_sha256"],
        "plan_sha256": digest_strings(json.dumps(r, sort_keys=True) for r in membership),
        "primary_development_group_overlap": 0,
        "feature_or_prediction_computed": False,
    }
    write_json({"provenance": result, "members": membership}, args.plan_out)
    write_json(result, args.summary_out)


if __name__ == "__main__":
    main()
