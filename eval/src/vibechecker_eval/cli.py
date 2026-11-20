import argparse
import json
import re
from pathlib import Path

from .registry import fetch, registry, select, sync_r2


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vibechecker-eval")
    cmds = parser.add_subparsers(dest="command", required=True)
    reference = cmds.add_parser("falcon-reference")
    reference.add_argument(
        "--pairs", type=int, default=64, help="Paired passages; zero uses all 2,207"
    )
    reference.add_argument("--seed", type=int, default=42)
    reference.add_argument("--cache", type=Path, default=Path("eval/.cache"))
    reference.add_argument("--out", type=Path, required=True)
    bake = cmds.add_parser("bakeoff")
    bake.add_argument("reports", nargs="+", type=Path)
    bake.add_argument("--out", type=Path, required=True)
    bake.add_argument(
        "--partial",
        action="store_true",
        help="Write incomplete evidence without selecting a release model",
    )
    bake.add_argument(
        "--rank-provisional",
        action="store_true",
        help="Rank measured candidates meeting memory and ESL limits",
    )
    bake.add_argument(
        "--rejected",
        type=Path,
        action="append",
        default=[],
        help="Over-cap preflight JSON (repeatable)",
    )
    preflight = cmds.add_parser(
        "memory-preflight", help="Record why a pair exceeded the M6 memory budget"
    )
    preflight.add_argument("--pair-family", required=True)
    preflight.add_argument("--bits", type=int, choices=(4, 6, 8), required=True)
    measurement = preflight.add_mutually_exclusive_group(required=True)
    measurement.add_argument(
        "--observed-pid",
        type=int,
        help="Measure a running candidate's lifetime physical footprint on macOS",
    )
    measurement.add_argument(
        "--projected-bytes", type=int, help="Projected unified footprint in bytes"
    )
    preflight.add_argument(
        "--basis", required=True, help="Describe the measurement or projection inputs"
    )
    preflight.add_argument("--out", type=Path, required=True)
    for name in ("baseline", "quick", "deep", "fetch", "sync"):
        cmd = cmds.add_parser(name)
        cmd.add_argument("--cache", type=Path, default=Path("eval/.cache"))
        cmd.add_argument("--registry", type=Path)
        cmd.add_argument(
            "--datasets",
            nargs="+",
            default=["liang"]
            if name == "baseline"
            else ["raid", "raid-attacks", "asap", "ellipse", "liang"]
            if name == "deep"
            else ["raid", "liang"],
        )
        cmd.add_argument("--commercial-only", action="store_true")
        if name in {"baseline", "quick", "deep"}:
            cmd.add_argument("--limit-per-class", type=int, default=0 if name == "baseline" else 64)
            cmd.add_argument("--seed", type=int, default=42)
            cmd.add_argument(
                "--version",
                default={"baseline": "hfopenai-liang-v1", "quick": "quick-v0", "deep": "phase-1"}[
                    name
                ],
            )
            cmd.add_argument("--reports", type=Path, default=Path("eval/reports"))
            cmd.add_argument("--previous", type=Path)
            cmd.add_argument("--trace-out", type=Path)
            cmd.add_argument("--compare-trace", type=Path)
            cmd.add_argument(
                "--enforce",
                action="store_true",
                help="Return nonzero unless quality and parity pass",
            )
        if name in {"quick", "deep"}:
            model = cmd.add_mutually_exclusive_group(required=True)
            model.add_argument("--model-out", type=Path)
            model.add_argument("--model-in", type=Path)
        if name == "deep":
            cmd.add_argument("--cohort", choices=["validation", "test"], default="test")
            cmd.add_argument("--pair-family", help="Base/instruct source family, e.g. Qwen2.5-7B")
            for gate in ("reference", "bakeoff", "load"):
                cmd.add_argument(f"--{gate}-report", type=Path)
        if name == "baseline":
            cmd.add_argument(
                "--roberta-dir", type=Path, help="Local pinned RoBERTa-large checkpoint"
            )
        if name == "sync":
            cmd.add_argument("direction", choices=["push", "pull"])
            cmd.add_argument("--bucket", default="vibechecker-artifacts")
    args = parser.parse_args(argv)
    if args.command in {"falcon-reference", "bakeoff", "memory-preflight"}:
        from .deep_runner import read, write_json
        from .experiments import bakeoff, memory_preflight, reference

        if args.command == "bakeoff":
            result = bakeoff(
                [read(path) for path in args.reports],
                partial=args.partial,
                rank_provisional=args.rank_provisional,
                rejected=[read(p) for p in args.rejected],
            )
            write_json(result, args.out)
            if args.partial:
                return 0
        elif args.command == "memory-preflight":
            memory_preflight(args)
            return 0
        else:
            result = reference(args)
        return int(not result["pass"])
    datasets = select(registry(args.registry), args.datasets, args.commercial_only)
    if args.command == "sync":
        sync_r2(datasets, args.cache, args.direction, args.bucket)
    elif args.command == "fetch":
        for data in datasets:
            for artifact in data.artifacts:
                print(data.id, artifact.name, fetch(artifact, args.cache).name)
    else:
        from .runner import run

        if args.limit_per_class < 0 or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*", args.version
        ):
            parser.error("Invalid sample size or version")
        if args.command == "deep":
            from .deep_runner import run_deep

            report = run_deep(args, datasets)
        else:
            report = run(args, datasets)
        print(
            json.dumps(
                {
                    "version": args.version,
                    "scored": report["metrics"]["pooled"]["count"],
                    "release_ready": report["release_ready"],
                }
            )
        )
        return int(args.enforce and not report["release_ready"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
