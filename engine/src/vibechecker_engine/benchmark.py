import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from . import FEATURE_NAMES, QuickEngine


def measure(engine, essay, runs):
    row = engine.extractor.extract(essay)
    prediction = engine.stacker.predict(row.values, row.word_count)
    durations = []
    for _ in range(runs):
        start = perf_counter()
        engine.analyze(essay)
        durations.append((perf_counter() - start) * 1000)
    timing = {
        "backend": engine.backend,
        "words": row.word_count,
        "runs": runs,
        "p50_ms": float(np.percentile(durations, 50)),
        "p95_ms": float(np.percentile(durations, 95)),
    }
    verdict = {k: prediction[k] for k in ("index", "band", "interval")}
    return timing, np.asarray(row.values), verdict


def main():
    parser = argparse.ArgumentParser(description="Measure warm Quick engine latency")
    parser.add_argument("essay", type=Path, help="Local, non-participant benchmark fixture")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument(
        "--compare-prefill",
        type=int,
        help="Compare a candidate Quick prefill to the Phase 0 64-token setting",
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    essay = args.essay.read_text(encoding="utf-8")
    engine = QuickEngine.from_env()
    if args.compare_prefill is None:
        timing, _, _ = measure(engine, essay, args.runs)
        print(json.dumps(timing))
        return
    engine.extractor.set_prefill(64)
    baseline, original, verdict = measure(engine, essay, args.runs)
    engine.extractor.set_prefill(args.compare_prefill)
    candidate, compared, new_verdict = measure(engine, essay, args.runs)
    print(
        json.dumps(
            {
                "baseline": baseline,
                "candidate": candidate,
                "prefill": args.compare_prefill,
                "absolute_feature_deltas": dict(
                    zip(FEATURE_NAMES, np.abs(original - compared), strict=True)
                ),
                "original_verdict": verdict,
                "candidate_verdict": new_verdict,
            },
            indent=2,
        )
    )
    if verdict != new_verdict:
        raise SystemExit("Displayed verdict differs on this fixture")


if __name__ == "__main__":
    main()
