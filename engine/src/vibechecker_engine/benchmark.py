import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from . import QuickEngine


def main():
    parser = argparse.ArgumentParser(description="Measure warm Quick engine latency")
    parser.add_argument("essay", type=Path, help="Local, non-participant benchmark fixture")
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    essay = args.essay.read_text(encoding="utf-8")
    engine = QuickEngine.from_env()
    warmup = engine.analyze(essay)
    durations = []
    for _ in range(args.runs):
        start = perf_counter()
        engine.analyze(essay)
        durations.append((perf_counter() - start) * 1000)
    print(
        json.dumps(
            {
                "backend": engine.backend,
                "words": warmup["wordCount"],
                "runs": args.runs,
                "p50_ms": float(np.percentile(durations, 50)),
                "p95_ms": float(np.percentile(durations, 95)),
            }
        )
    )


if __name__ == "__main__":
    main()
