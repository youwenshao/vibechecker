"""Exercise the deployed pair reader on the pinned SmolLM2 CPU fixtures."""

import json
import math
import os
from pathlib import Path

from fetch_weights import fetch_checkpoints
from vibechecker_engine.deep import PairExtractor

BASE = "HuggingFaceTB/SmolLM2-135M"
INSTRUCT = "HuggingFaceTB/SmolLM2-135M-Instruct"
CHECKPOINTS = (
    (
        BASE,
        "93efa2f097d58c2a74874c7e644dbc9b0cee75a2",
        "80521b40281d6ce74e35c9282c22539e75aa0ac8578892b2a59955ef78d55da1",
    ),
    (
        INSTRUCT,
        "12fd25f77366fa6b3b4b768ec3050bf629380bac",
        "5af571cbf074e6d21a03528d2330792e532ca608f24ac70a143f6b369968ab8c",
    ),
)


def main():
    directory = Path.home() / ".cache" / "vibechecker" / "smol-pair"
    fetch_checkpoints(directory, CHECKPOINTS)
    os.environ.update(
        {
            "VIBECHECKER_BACKEND": "mlx-cpu",
            "VIBECHECKER_PAIR_OBSERVER": str(directory / BASE.split("/")[-1]),
            "VIBECHECKER_PAIR_PERFORMER": str(directory / INSTRUCT.split("/")[-1]),
        }
    )
    pair = PairExtractor.from_env()
    # Opening of Melville's public-domain Moby-Dick, chapter one.
    e3, e4 = pair.score(
        "Call me Ishmael. Some years ago — never mind how long precisely — "
        "having little or no money in my purse, and nothing particular "
        "to interest me on shore, I thought I would sail about a little "
        "and see the watery part of the world."
    )
    if pair.backend.name != "mlx-cpu" or not (math.isfinite(e3) and math.isfinite(e4)):
        raise RuntimeError("Expected finite Deep signals on MLX CPU")
    print(json.dumps({"backend": pair.backend.name, "e3": e3, "e4": e4}))


if __name__ == "__main__":
    main()
