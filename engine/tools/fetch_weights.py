"""Fetch the two Phase 0 checkpoints by immutable revision and check the weight hashes."""

import argparse
import hashlib
import os
from pathlib import Path

from huggingface_hub import snapshot_download

WEIGHTS = (
    (
        "Qwen/Qwen2.5-0.5B",
        "060db6499f32faf8b98477b0a26969ef7d8b9987",
        "88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342",
    ),
    (
        "GeorgeDrayson/modernbert-ai-detection-raid-mage",
        "e047d9c56f51a7e5c5ef5b0dd556f519bb9dd624",
        "2ae8059c621795fc490353bbd920bc3672e6eaf8ad66ddb7c015b4ecb0129218",
    ),
)


def fetch_checkpoints(directory, checkpoints):
    for repo, revision, checksum in checkpoints:
        dest = directory / repo.split("/")[-1]
        snapshot_download(
            repo,
            revision=revision,
            local_dir=dest,
            allow_patterns=["*.safetensors", "*.json", "*.txt", "LICENSE*", "README.md"],
            ignore_patterns=["*/*"],
        )
        with (dest / "model.safetensors").open("rb") as weights:
            if hashlib.file_digest(weights, "sha256").hexdigest() != checksum:
                raise RuntimeError(f"Weight checksum mismatch for {repo}")
        print(f"Verified {repo}@{revision} in {os.fspath(dest)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    fetch_checkpoints(args.directory, WEIGHTS)


if __name__ == "__main__":
    main()
