"""Replay a private research corpus cache on the workstation's CPU and RTX GPU."""

import argparse
import gzip
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from .deep_runner import write_json
from .loaders import examples, fingerprint
from .prospective import DATASETS, digest, manifest
from .registry import registry, select, sha256


def cache_fixtures(trace, cache, out):
    """Write only the pinned historical fixtures into a private research cache."""
    wanted = trace["scores"]
    datasets = select(registry(), DATASETS)
    if (
        digest(wanted) != trace["scope"]["scored_ids_sha256"]
        or manifest(datasets) != trace["manifest"]
    ):
        raise ValueError("Historical cohort commitment differs")
    seen = set()
    with TemporaryDirectory(dir=out.parent) as tmp:
        private = Path(tmp) / "fixtures.gz"
        with gzip.open(private, "xt", encoding="utf8") as stream:
            for item in examples(datasets, cache):
                key = fingerprint(item.text)
                if key in wanted and key not in seen:
                    stream.write(json.dumps([key, item.text]) + "\n")
                    seen.add(key)
        if seen != wanted.keys():
            raise ValueError("Missing historical fixtures")
        os.link(private, out)


def expand_cpu_linears(pair):
    """Evaluate the pinned affine Q4 projections with dense CPU GEMM in checkpoint dtype."""
    import mlx.core as mx
    import torch
    from mlx import nn
    from mlx.utils import tree_flatten, tree_unflatten

    class CpuLinear(nn.Module):
        def __init__(self, layer):
            super().__init__()
            if layer.bits != 4 or layer.mode != "affine" or layer.group_size != 64:
                raise ValueError("Expected the frozen affine Q4 pair")
            self.dense = torch.from_dlpack(
                mx.dequantize(
                    layer.weight, layer.scales, layer.biases, bits=4, group_size=64, stream=mx.cpu
                )
            )
            self.bias = layer.get("bias")

        def __call__(self, x):
            y = mx.array(torch.nn.functional.linear(torch.from_dlpack(x), self.dense))
            return y if self.bias is None else y + self.bias

    for model in (pair.observer, pair.performer):
        modules = tree_flatten(model.leaf_modules(), is_leaf=nn.Module.is_module)
        replacements = [
            (name, CpuLinear(m)) for name, m in modules if isinstance(m, nn.QuantizedLinear)
        ]
        if not replacements:
            raise ValueError("No Q4 projections to expand")
        model.update_modules(tree_unflatten(replacements))


def replay(reference, fixtures, output, dense_cpu=False):
    from vibechecker_engine.deep import DeepEngine

    start = perf_counter()
    if sha256(Path(os.environ["VIBECHECKER_DEEP_MODEL"])) != reference["model_sha256"]:
        raise ValueError("Unexpected frozen artifact")
    if os.environ.get("VIBECHECKER_BACKEND") == "mlx-cuda":
        import mlx.core as mx

        # Leave room for the eager Torch encoder on the same card.
        mx.set_cache_limit(512 * 1024**2)
        mx.set_memory_limit(23 * 1024**3)
    engine = DeepEngine.from_env()
    if (
        engine.extractor.identity != reference["weights"]
        or engine.extractor.quick.lm.chunk_size != reference["quick_prefill"]
    ):
        raise ValueError("Checkpoint manifest or prefill differs")
    backend = engine.backend
    if dense_cpu:
        if backend != "mlx-cpu":
            raise ValueError("Dense CPU reference requires the CPU backend")
        expand_cpu_linears(engine.extractor.pair.backend)
        backend = "mlx-cpu-dense-q4"
    scores, sentences = {}, {}
    with gzip.open(fixtures, "rt", encoding="utf8") as stream:
        for line in stream:
            key, value = json.loads(line)
            if fingerprint(value) != key or key not in reference["scores"] or key in scores:
                raise ValueError("Fixture identity differs")
            result = engine.analyze(value)
            scores[key] = result["index"]
            sentences[key] = [[s["start"], s["end"], s["score"]] for s in result["sentences"]]
            if len(scores) == 1 or len(scores) % 10 == 0:
                print(
                    f"{backend} {len(scores)} documents, {perf_counter() - start:.1f}s",
                    flush=True,
                )
    if scores.keys() != reference["scores"].keys():
        raise ValueError("Incomplete parity replay")
    trace = dict(
        reference,
        backend=backend,
        scores=scores,
        sentences=sentences,
        elapsed_seconds=perf_counter() - start,
    )
    write_json(trace, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument(
        "--dense-cpu", action="store_true", help="Expand Q4 projections for the CPU reference"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--export-from-cache", type=Path)
    group.add_argument("--trace-out", type=Path)
    args = parser.parse_args()
    trace = json.loads(args.reference.read_bytes())
    if args.export_from_cache:
        os.umask(0o077)
        cache_fixtures(trace, args.export_from_cache, args.fixtures)
    else:
        replay(trace, args.fixtures, args.trace_out, args.dense_cpu)


if __name__ == "__main__":
    main()
