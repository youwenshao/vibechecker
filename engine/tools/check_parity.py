"""Measure the pinned Quick LM's next-token statistics on an authorized fixture."""

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from vibechecker_engine.backends.mlx import MLXBackend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lm", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--tokens", type=int, default=128)
    parser.add_argument("--backend", choices=["mlx-metal", "mlx-cuda"], default="mlx-metal")
    args = parser.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.lm, local_files_only=True)
    ids = tokenizer(
        args.fixture.read_text(encoding="utf-8"),
        add_special_tokens=False,
        truncation=True,
        max_length=args.tokens,
    )["input_ids"]
    if len(ids) < 2:
        parser.error("Fixture must contain at least two tokens")
    cpu = MLXBackend.from_path(args.lm, "mlx-cpu").token_stats(ids)
    accelerator = MLXBackend.from_path(args.lm, args.backend).token_stats(ids)
    model = AutoModelForCausalLM.from_pretrained(
        args.lm,
        local_files_only=True,
        use_safetensors=True,
        dtype=torch.float32,
        attn_implementation="eager",
    )
    with torch.inference_mode():
        logits = model(torch.tensor([ids[:-1]])).logits[0].float()
        lp = logits.log_softmax(-1)
        observed = lp.gather(1, torch.tensor(ids[1:])[:, None])
        reference = {
            "logp": observed[:, 0].numpy(),
            "rank": (
                1 + (logits > logits.gather(1, torch.tensor(ids[1:])[:, None])).sum(1)
            ).numpy(),
            "entropy": -(lp.exp() * lp).sum(1).numpy(),
        }
    comparisons = {}
    for name, other in (("mlx_cpu", cpu.__dict__), ("torch_cpu_fp32", reference)):
        comparisons[name] = {}
        for field in ("logp", "rank", "entropy"):
            delta = abs(getattr(accelerator, field) - other[field])
            comparisons[name][field] = {
                "mean_abs_delta": float(delta.mean()),
                "max_abs_delta": float(delta.max()),
            }
    print(
        json.dumps(
            {"backend": args.backend, "tokens_scored": len(ids) - 1, "comparisons": comparisons},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
