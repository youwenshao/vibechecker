"""Fit the bounded Phase 1.1 policies and replay their frozen decisions on committed cohorts."""

import argparse
from collections import Counter
from pathlib import Path
from time import perf_counter

from threadpoolctl import threadpool_limits

from .academic_addition import matrix
from .deep_cohort import fold
from .deep_runner import read, write_json
from .loaders import examples, fingerprint
from .metrics import Observation, gates
from .prospective import DATASETS, digest, manifest, plan_digest, publish
from .refit import load_rows
from .refit_cache import CALIBRATION, VALIDATION
from .registry import registry, select, sha256
from .rewrite_diagnostics import effective_training
from .rewrite_refit import displayed
from .runner import observation
from .source_groups import source_key
from .subgroup_policy import fit, scorecard

REPORTS = Path("eval/reports/phase-1")
MODEL_SHA = "aeafbb70201caec3029b24799faedd8fee89aacf5ef1bdf09e1eee2673b82d9b"
BASELINE = {"base_high": 24, "powers": {}, "cutoffs": {}}


def cached_observations(model, rows, names):
    indices = displayed(model.stacker, matrix(rows, model.probe), rows)
    out = []
    for r, index in zip(rows, indices, strict=True):
        fields = dict(names[k].split("/", 1) for k in r.strata)
        out.append(
            Observation(
                r.id,
                r.label,
                index / 100,
                fields["dataset"],
                fields["split"],
                fields["genre"],
                fields["writer"],
                fields["generator"],
                fields["attack"],
                r.words,
                None,
            )
        )
    return out


def fit_policy(args):
    from vibechecker_engine.deep import DeepModel

    receipts = read(REPORTS / "academic-addition-input.json")["file_sha256"]
    if (
        sha256(args.model) != MODEL_SHA
        or sha256(args.parent) != receipts["v1_parent"]
        or sha256(args.features) != receipts["base_features"]
    ):
        raise ValueError("Unexpected model or feature cache")
    model, parent = (DeepModel.load(p) for p in (args.model, args.parent))
    _, cached, names, _, _ = load_rows(args.features, parent, receipts["v1_parent"], False)
    prior = REPORTS / "calibration-selection.json"
    if sha256(prior) != receipts["v2_selection"]:
        raise ValueError("Prior source exclusions differ")
    effective = effective_training(args.cache, cached, read(prior))
    calibration = cached_observations(model, effective[CALIBRATION], names)
    validation = cached_observations(model, cached[VALIDATION], names)
    hi = model.stacker.high_threshold
    if hi != BASELINE["base_high"]:
        raise ValueError("Unexpected incumbent threshold")
    candidates = {
        "v4": BASELINE,
        "threshold": fit(calibration, hi),
        "guarded": fit(calibration, hi, guarded=True),
        "adjusted": fit(calibration, hi, adjust=True),
    }
    mixed = model.stacker.low_threshold / 100
    cards = {name: scorecard(validation, p, mixed) for name, p in candidates.items()}
    publish(
        {
            "model_sha256": MODEL_SHA,
            "cache_sha256": receipts["base_features"],
            "calibration_ids": digest(r.id for r in calibration),
            "calibration_count": len(calibration),
            "validation_ids": digest(r.id for r in validation),
            "validation_count": len(validation),
            "mixed": mixed,
            "policies": candidates,
        },
        args.out,
    )
    write_json(cards, args.validation)


def combine(audit, college, group_ids):
    if not college or any(r.dataset != "liang/college-human" or r.label for r in college):
        raise ValueError("Coverage supplement requires the failing admissions cohort")
    a, b = ({r.id for r in rows} for rows in (audit, college))
    if (
        len(a) != len(audit)
        or len(b) != len(college)
        or a & b
        or {group_ids[k] for k in a} & {group_ids[k] for k in b}
    ):
        raise ValueError("Overlapping documents or sources in combined sensitivity analysis")
    return [*audit, *college]


def historical_groups(trace, report):
    if (
        trace["scope"] != report["scope"]
        or trace["version"] != report["version"]
        or report["model_sha256"] != MODEL_SHA
        or trace["model_sha256"] != MODEL_SHA
        or trace["weights"] != report["weights"]
        or trace["backend"] != report["backend"]
        or trace["quick_prefill"] != report["quick_prefill"]
        or digest(trace["scores"]) != report["scope"]["scored_ids_sha256"]
        or len(trace["scores"]) != report["metrics"]["pooled"]["count"]
    ):
        raise ValueError("Trace and published scorecard differ")
    return trace["scores"]


def evaluate(args):
    from vibechecker_engine.text import Refusal, count_words, prepare, validate

    started = perf_counter()
    policy = read(args.policy)
    if sha256(args.policy) != args.policy_sha256 or policy["model_sha256"] != MODEL_SHA:
        raise ValueError("Unexpected policy or model")
    datasets = select(registry(), DATASETS)
    reports = [read(REPORTS / p / "report.json") for p in ("", "prospective")]
    traces = [read(p) for p in (args.original, args.audit)]
    original, prospective = [historical_groups(t, r) for t, r in zip(traces, reports, strict=True)]
    plan = read(REPORTS / "prospective-audit-reservation.json")
    if (
        plan_digest(plan) != traces[1]["scope"]["audit_plan_sha256"]
        or manifest(datasets) != plan["input_manifest"]
        or original.keys() & prospective.keys()
    ):
        raise ValueError("Unexpected reservation, corpus or overlapping final traces")
    members = dict(plan["members"])
    if not prospective.keys() <= members.keys():
        raise ValueError("Unreserved prospective member")
    rows, groups = {}, {}
    dispositions = Counter()
    college_seen = set()
    for item in examples(datasets, args.cache):
        key = fingerprint(item.text)
        if item.dataset == "liang/college-human":
            if key in college_seen:
                reason = "duplicate"
            elif not 300 <= count_words(item.text) <= 2500:
                reason = "outside_length_band"
            elif fold(item, "bakeoff") == 0:
                reason = "development_fold"
            elif key in original:
                reason = "historical_scored"
            else:
                try:
                    validate(prepare(item.text), "deep")
                except Refusal as exc:
                    reason = f"historical_refused/{exc.code}"
                else:
                    raise ValueError("An eligible unused final college essay requires reservation")
            dispositions[reason] += 1
            college_seen.add(key)
        if key in rows or (key not in original and key not in prospective):
            continue
        group = fingerprint(source_key(item, document_id=key))
        if key in prospective and members[key] != group:
            raise ValueError("Prospective source mismatch")
        groups[key] = group
        rows[key] = observation(
            item,
            count_words(item.text),
            (original[key] if key in original else prospective[key]) / 100,
            None,
        )
    original_rows, audit_rows = (
        [rows[key] for key in scores] for scores in (original, prospective)
    )
    if {groups[r.id] for r in original_rows} & {groups[r.id] for r in audit_rows}:
        raise ValueError("Historical and prospective sources overlap")
    if plan["pool"]["strata"].get("dataset/liang/college-human", 0):
        raise ValueError("Independent admissions sources remain available for reservation")
    college = [r for r in original_rows if r.dataset == "liang/college-human"]
    combined = combine(audit_rows, college, groups)
    short = read(args.short)
    pinned = next(a for a in registry()["liang"].artifacts if a.name == "toefl")
    short_items = [
        r for r in examples([registry()["liang"]], args.cache) if r.dataset == "liang/toefl"
    ]
    if (
        short["corpus_sha256"] != pinned.sha256
        or short["model_sha256"] != MODEL_SHA
        or short["quick_prefill"] != 512
        or short["backend"] != "mlx-metal"
        or len(short_items) != 91
        or len(short["scores"]) != 91
    ):
        raise ValueError("Incomplete or incompatible short-text measurement")
    short_rows = []
    for i, (entry, item) in enumerate(zip(short["scores"], short_items, strict=True), 1):
        words = count_words(item.text)
        if (
            entry["row"] != i
            or entry["id"] != fingerprint(item.text)
            or entry["words"] != words
            or not 0 < words < 300
        ):
            raise ValueError("Short-text member differs")
        short_rows.append(observation(item, words, entry["index"] / 100, None))
    samples = {
        "original": original_rows,
        "prospective": audit_rows,
        "combined_replay": combined,
        "toefl_short": short_rows,
        "toefl_distinct": list({r.id: r for r in short_rows}.values()),
    }
    cards = {
        sample: {
            name: scorecard(data, p, policy["mixed"]) for name, p in policy["policies"].items()
        }
        for sample, data in samples.items()
    }
    for sample, report in zip(("original", "prospective"), reports, strict=True):
        for key, values in report["metrics"].items():
            actual = cards[sample]["v4"][key]
            for field in ("count", "ai_count", "ece", "brier", "auroc", "tpr_at_1pct_fpr"):
                if actual[field] != values[field] and (
                    actual[field] is None
                    or values[field] is None
                    or abs(actual[field] - values[field]) > 1e-12
                ):
                    raise ValueError(f"Historical metric mismatch: {sample}/{key}/{field}")
            if actual["fpr_high"] != values["fpr_high"]:
                raise ValueError(f"Historical high-band mismatch: {sample}/{key}")
    previous = REPORTS.parent / "deep-qwen7b-q4-p512-v2" / "report.json"
    if sha256(previous) != reports[0]["regression_reference"]["report_sha256"]:
        raise ValueError("Historical regression reference differs")
    reference_metrics = read(previous)["metrics"]
    checks = {
        sample: {
            name: gates(
                groups,
                deep=True,
                quick=False,
                require_college=sample == "prospective",
                previous=reference_metrics if sample == "original" else None,
            )["checks"]
            for name, groups in cards[sample].items()
        }
        for sample in ("original", "prospective")
    }
    write_json(
        {
            "policy_sha256": args.policy_sha256,
            "model_sha256": MODEL_SHA,
            "trace_sha256": [sha256(args.original), sha256(args.audit)],
            "reservation_sha256": plan_digest(plan),
            "short_trace_sha256": sha256(args.short),
            "short_elapsed_seconds": short["elapsed_seconds"],
            "short_product_refusals": short["product_refusals"],
            "short_words": [min(r.words for r in short_rows), max(r.words for r in short_rows)],
            "college_disposition": dict(dispositions),
            "prospective_pool_college": plan["pool"]["strata"].get(
                "dataset/liang/college-human", 0
            ),
            "combined_reused_historical": len(college),
            "combined_new_independent_college": 0,
            "combined_ids": digest(r.id for r in combined),
            "elapsed_seconds": perf_counter() - started,
            "metrics": cards,
            "checks": checks,
            "release_eligible": False,
        },
        args.out,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("fit")
    for name in ("model", "parent", "features", "cache", "out", "validation"):
        p.add_argument("--" + name, type=Path, required=True)
    p = sub.add_parser("evaluate")
    for name in ("policy", "original", "audit", "cache", "short", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--policy-sha256", required=True)
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        (fit_policy if args.command == "fit" else evaluate)(args)


if __name__ == "__main__":
    main()
