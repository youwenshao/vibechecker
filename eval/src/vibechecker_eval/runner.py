from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from time import perf_counter

from .loaders import examples, fingerprint
from .metrics import Observation, backend_parity, gates, summarize
from .registry import sha256


def sample(stream, limit, seed, count_words, *, quick_length=True):
    """Reservoir sampling keeps evaluation memory bounded even on the full RAID corpus."""
    selected = defaultdict(list)
    counts, skipped = Counter(), Counter()
    seen = set()
    rng = random.Random(seed)
    for item in stream:
        n = count_words(item.text)
        if quick_length and not 150 <= n <= 5000:
            skipped[f"{item.dataset}/length"] += 1
            continue
        digest = fingerprint(item.text)
        if digest in seen:
            skipped[f"{item.dataset}/duplicate"] += 1
            continue
        seen.add(digest)
        key = (item.dataset, item.split, item.label)
        counts[key] += 1
        if not limit or len(selected[key]) < limit:
            selected[key].append((item, n))
        else:
            pos = rng.randrange(counts[key])
            if pos < limit:
                selected[key][pos] = (item, n)
    return [r for k in sorted(selected) for r in selected[k]], skipped


def observation(item, n, score, latency):
    return Observation(
        fingerprint(item.text),
        item.label,
        score,
        item.dataset,
        item.split,
        item.genre,
        item.writer,
        item.generator,
        item.attack,
        n,
        latency,
    )


def write_report(report, directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf8"
    )
    lines = [
        f"# {report['version']}",
        "",
        report["description"],
        "",
        f"Backend `{report['backend']}`. Scored {report['metrics']['pooled']['count']} held-out documents.",
        "",
        "## Results",
        "",
        "| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]

    def display(v):
        return "—" if v is None else f"{v:.4f}"

    for name, group in report["metrics"].items():
        rate = group["fpr_high"]
        fpr = display(rate["rate"])
        if rate["wilson95"] is not None:
            fpr += " (" + ", ".join(map(display, rate["wilson95"])) + ")"
        numbers = [display(group[k]) for k in ("auroc", "tpr_at_1pct_fpr", "ece", "brier")]
        lines.append(f"| {name} | {group['count']} | " + " | ".join(numbers) + f" | {fpr} |")
    lines += [
        "",
        "## Quick acceptance gates",
        "",
        "| Measure | Observed | Gate | Status |",
        "|---|---:|---:|---|",
    ]
    for name, gate in report["gates"]["checks"].items():
        lines.append(f"| {name} | {display(gate['value'])} | {gate['target']} | {gate['status']} |")
    lines += [
        "",
        "The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.",
        "",
    ]
    (directory / "report.md").write_text("\n".join(lines), encoding="utf8")


def run(args, datasets):
    from vibechecker_engine.text import Refusal, count_words

    quick = args.command == "quick"
    chosen, skipped = sample(
        examples(datasets, args.cache),
        args.limit_per_class,
        args.seed,
        count_words,
        quick_length=quick,
    )
    rows = []
    fitted = None
    fit_counts = {}
    comparator = None
    if quick:
        from vibechecker_engine import FeatureExtractor, QuickStacker

        extractor = FeatureExtractor.from_env()
        backend = extractor.backend
        if args.model_in:
            model = QuickStacker.load(args.model_in)
            fitted = sha256(args.model_in)
        else:
            features = defaultdict(list)
            for item, _ in chosen:
                if item.split != "test":
                    try:
                        x = extractor.extract(item.text)
                    except Refusal as e:
                        skipped[f"{item.dataset}/{e.code}"] += 1
                        continue
                    features[item.split].append((x, item.label))
            train, cal = features["train"], features["calibration"]
            for name, part in (("train", train), ("calibration", cal)):
                fit_counts[name] = dict(Counter(y for _, y in part))
                if set(fit_counts[name]) != {0, 1}:
                    raise ValueError(f"{name} requires both verified human and generated samples")
            model = QuickStacker.fit(
                [x.values for x, _ in train],
                [y for _, y in train],
                [x.values for x, _ in cal],
                [y for _, y in cal],
                [x.word_count for x, _ in cal],
                seed=args.seed,
            )
            args.model_out.parent.mkdir(parents=True, exist_ok=True)
            model.save(args.model_out)
            fitted = sha256(args.model_out)
        mixed, high = model.low_threshold / 100, model.high_threshold / 100
    else:
        backend, mixed, high = "archived-hfopenai", 0.5, 0.9
        if args.roberta_dir:
            from .roberta import RobertaBaseline

            comparator = RobertaBaseline(args.roberta_dir)
            backend, fitted = comparator.backend, comparator.digest

    for item, n in chosen:
        if item.split != "test":
            continue
        if quick:
            start = perf_counter()
            try:
                x = extractor.extract(item.text)
            except Refusal as e:
                skipped[f"{item.dataset}/{e.code}"] += 1
                continue
            score = model.predict(x.values, x.word_count)["index"] / 100
            latency = (perf_counter() - start) * 1000
        elif comparator is not None:
            start = perf_counter()
            score = comparator.score(item.text)
            latency = (perf_counter() - start) * 1000
        else:
            score, latency = item.archived_score, None
            if score is None:
                raise ValueError("Missing archived baseline prediction")
        rows.append(observation(item, n, score, latency))
    manifest = {
        d.id: {"version": d.version, "sha256": [a.sha256 for a in d.artifacts]} for d in datasets
    }
    trace = {
        "version": args.version,
        "backend": backend,
        "manifest": manifest,
        "model_sha256": fitted,
        "scores": {r.id: round(r.score * 100, 8) for r in rows},
    }
    if args.trace_out:
        args.trace_out.parent.mkdir(parents=True, exist_ok=True)
        args.trace_out.write_text(json.dumps(trace) + "\n", encoding="utf8")
    parity = None
    if args.compare_trace:
        ref = json.loads(args.compare_trace.read_bytes())
        if ref.get("model_sha256") != fitted:
            raise ValueError("Parity requires the same fitted stacker")
        parity = backend_parity(trace, ref)
    summary = summarize(rows, mixed, high)
    previous = json.loads(args.previous.read_bytes()) if args.previous else None
    scope = {
        "seed": args.seed,
        "limit_per_class_per_dataset_split": args.limit_per_class,
        "commercial_only": args.commercial_only,
        "manifest": manifest,
        "scored_ids_sha256": fingerprint(" ".join(sorted(trace["scores"]))),
    }
    if previous and previous["scope"] != scope:
        raise ValueError("Regression comparison requires identical evaluation cohorts")
    gate = gates(summary, quick=quick, previous=previous["metrics"] if previous else None)
    report = {
        "version": args.version,
        "mode": "quick" if quick else "baseline",
        "description": (
            "Real Quick pipeline. RAID and MAGE overlap the encoder's published training domains. "
            "Hewlett is the study's US comparison cohort. Individual native-language status is unverified."
            if quick
            else (
                "Locally measured RoBERTa-large GPT-2 output detector, first 510 tokens per document. "
                if comparator is not None
                else "Replay of Liang et al.’s archived HFOpenAI scores. "
            )
            + "All available essay lengths are included for the baseline. Mixed and high thresholds are 0.50 and 0.90. "
            + "Short essays in this offline comparison receive a length refusal in the Quick service. "
            + "Hewlett is the US comparison cohort. Individual native-language status is unverified."
        ),
        "backend": backend,
        "model_sha256": fitted,
        "scope": scope,
        "fit_counts": fit_counts,
        "skipped": dict(sorted(skipped.items())),
        "thresholds": {"mixed": mixed, "high": high},
        "metrics": summary,
        "sentence_f1": None,
        "parity": parity,
        "gates": gate,
        "release_ready": gate["eligible"] and parity is not None and parity["pass"],
    }
    write_report(report, args.reports / args.version)
    return report
