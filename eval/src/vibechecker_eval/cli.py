import argparse
import json
import re
from pathlib import Path

from .registry import fetch, registry, select, sync_r2


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vibechecker-eval")
    cmds = parser.add_subparsers(dest="command", required=True)
    for name in ("baseline", "quick", "fetch", "sync"):
        cmd = cmds.add_parser(name)
        cmd.add_argument("--cache", type=Path, default=Path("eval/.cache"))
        cmd.add_argument("--registry", type=Path)
        cmd.add_argument(
            "--datasets", nargs="+", default=["liang"] if name == "baseline" else ["raid", "liang"]
        )
        cmd.add_argument("--commercial-only", action="store_true")
        if name in {"baseline", "quick"}:
            cmd.add_argument("--limit-per-class", type=int, default=0 if name == "baseline" else 64)
            cmd.add_argument("--seed", type=int, default=42)
            cmd.add_argument(
                "--version", default="hfopenai-liang-v1" if name == "baseline" else "quick-v0"
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
        if name == "quick":
            model = cmd.add_mutually_exclusive_group(required=True)
            model.add_argument("--model-out", type=Path)
            model.add_argument("--model-in", type=Path)
        if name == "baseline":
            cmd.add_argument(
                "--roberta-dir", type=Path, help="Local pinned RoBERTa-large checkpoint"
            )
        if name == "sync":
            cmd.add_argument("direction", choices=["push", "pull"])
            cmd.add_argument("--bucket", default="vibechecker-artifacts")
    args = parser.parse_args(argv)
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
