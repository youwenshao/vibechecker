"""Content-addressed inputs. A changed upstream object cannot silently enter training."""

from __future__ import annotations

import os
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import file_digest
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

import yaml


@dataclass(frozen=True)
class Artifact:
    name: str
    url: str
    sha256: str
    split: str


@dataclass(frozen=True)
class Dataset:
    id: str
    source: str
    version: str
    license: str
    commercial_ok: bool
    share_alike: bool
    use: str
    strata: list[str]
    artifacts: list[Artifact]


def registry(path: Path | None = None) -> dict[str, Dataset]:
    if path is None:
        installed = Path(__file__).with_name("registry.yaml")
        path = (
            installed
            if installed.exists()
            else Path(__file__).resolve().parents[2] / "registry.yaml"
        )
    result = {}
    for raw in yaml.safe_load(path.read_text(encoding="utf8"))["datasets"]:
        artifacts = [Artifact(**item) for item in raw.pop("artifacts")]
        data = Dataset(**raw, artifacts=artifacts)
        if data.id in result or data.use not in {"train_eval", "eval", "excluded"}:
            raise ValueError("Invalid dataset registry")
        for a in artifacts:
            if not re.fullmatch(r"[0-9a-f]{64}", a.sha256):
                raise ValueError(f"Invalid source digest for {data.id}")
            if a.split not in {"grouped", "test"} or not a.url.startswith("https://"):
                raise ValueError(f"Invalid artifact for {data.id}")
        if data.use != "excluded" and not artifacts:
            raise ValueError(f"Missing artifacts for {data.id}")
        result[data.id] = data
    return result


def select(datasets, names, commercial_only=False):
    selected = []
    for name in dict.fromkeys(names):
        data = datasets[name]
        if data.use == "excluded":
            raise ValueError(f"{name} is excluded in the registry")
        if commercial_only and not data.commercial_ok:
            continue
        selected.append(data)
    if not selected:
        raise ValueError("No eligible datasets")
    return selected


def sha256(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


@contextmanager
def verified_output(artifact, cache):
    cache.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=cache, delete=False) as temp:
        path = Path(temp.name)
    try:
        yield path
        if sha256(path) != artifact.sha256:
            raise ValueError(f"Checksum mismatch for {artifact.name}")
        path.replace(cache / artifact.sha256)
    finally:
        path.unlink(missing_ok=True)


def fetch(artifact, cache):
    path = cache / artifact.sha256
    if path.is_file():
        if sha256(path) != artifact.sha256:
            raise ValueError(f"Corrupt cached {artifact.name}")
        return path
    with (
        verified_output(artifact, cache) as temp,
        urlopen(artifact.url, timeout=90) as source,
        temp.open("wb") as target,
    ):
        shutil.copyfileobj(source, target)
    return path


def sync_r2(datasets, cache, direction, bucket):
    import boto3

    s3 = boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT_URL"], region_name="auto")
    for dataset in datasets:
        for artifact in dataset.artifacts:
            key = f"datasets/sha256/{artifact.sha256}"
            if direction == "push":
                s3.upload_file(str(fetch(artifact, cache)), bucket, key)
            else:
                with verified_output(artifact, cache) as temp:
                    s3.download_file(bucket, key, str(temp))
