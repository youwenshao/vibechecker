"""Convert a local full-precision pair member for a reproducible quantization comparison."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import mlx.core as mx
from mlx_lm.utils import quantize_model, save_model
from transformers import AutoTokenizer
from vibechecker_engine.backends.pair import load_pair_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--bits", type=int, choices=(4, 6, 8), required=True)
    args = parser.parse_args()
    if args.destination.exists():
        parser.error("Destination must be a new directory")
    if sys.platform == "darwin":
        mx.set_memory_limit(18 * 1024**3)
        mx.set_cache_limit(512 * 1024**2)
    # Let the shard writer materialize weights as it needs them on the shared mini.
    model, config = load_pair_model(args.source, lazy=True)
    if config.get("quantization") or config.get("quantization_config"):
        parser.error("Start each candidate from the same full-precision checkpoint")
    packed, config = quantize_model(model, config, group_size=64, bits=args.bits)
    tokenizer = AutoTokenizer.from_pretrained(args.source, local_files_only=True)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.destination.parent) as work:
        output = Path(work) / "model"
        save_model(output, packed, donate_model=True)
        tokenizer.save_pretrained(output)
        (output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf8")
        output.rename(args.destination)


if __name__ == "__main__":
    main()
