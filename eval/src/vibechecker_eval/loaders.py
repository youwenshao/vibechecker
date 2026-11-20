"""Translate publisher labels to 1 for generated text. Preserve related RAID prompts in one split."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass

from .registry import fetch


@dataclass(frozen=True)
class Example:
    text: str
    label: int
    dataset: str
    split: str
    genre: str
    writer: str = "unknown"
    generator: str = "unknown"
    attack: str = "none"
    archived_score: float | None = None


def fingerprint(text):
    return hashlib.sha256(" ".join(text.casefold().split()).encode()).hexdigest()


def partition(group):
    bucket = int(fingerprint(group)[:8], 16) % 10
    return "train" if bucket < 6 else "calibration" if bucket < 8 else "test"


def raid_examples(rows, dataset_id="raid"):
    for r in rows:
        label = int(r["model"] != "human")
        yield Example(
            r["generation"],
            label,
            dataset_id,
            partition("raid:" + r["source_id"]),
            "other",
            generator=r["model"],
            attack=r["attack"],
        )


def human_essays(rows, name):
    seen = set()
    for r in rows:
        text = r["full_text"]
        group = fingerprint(text)
        if group in seen:
            continue
        seen.add(group)
        status = r.get("ell_status", r.get("ELL_status", "")).lower().strip()
        writer = (
            "ESL"
            if name == "ellipse" or status in {"yes", "ell", "english language learner", "1"}
            else "unknown"
        )
        yield Example(text, 0, name, partition(group), "essay", writer, "human")


def read_artifact(dataset, artifact, path):
    if dataset.id == "liang":
        label = int(artifact.name == "college-ai")
        writer = {"toefl": "ESL", "hewlett": "native_proxy"}.get(artifact.name, "unknown")
        for r in json.loads(path.read_bytes()):
            yield Example(
                r["document"],
                label,
                "liang/" + artifact.name,
                "test",
                "essay",
                writer,
                "gpt-3" if label else "human",
                archived_score=float(r["score"]),
            )
    elif dataset.id in {"raid", "raid-attacks"}:
        if artifact.name.endswith(".parquet"):
            import pyarrow.parquet as pq

            for batch in pq.ParquetFile(path).iter_batches(
                batch_size=1024, columns=["generation", "source_id", "model", "attack"]
            ):
                yield from raid_examples(batch.to_pylist(), dataset.id)
        else:
            with path.open(encoding="utf-8-sig", newline="") as f:
                yield from raid_examples(csv.DictReader(f))
    elif dataset.id == "mage":
        with path.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                label = 1 - int(r["label"])
                if label not in {0, 1}:
                    raise ValueError("Invalid MAGE label")
                src = r["src"]
                yield Example(
                    r["text"],
                    label,
                    "mage",
                    "test",
                    "other",
                    generator=src.partition("_machine_")[-1] if label else "human",
                )
    elif dataset.id == "padben":
        for r in json.loads(path.read_bytes()):
            yield Example(
                r["sentence"], int(r["label"]), "padben", "test", "other", attack="paraphrase"
            )
    elif dataset.id == "asap":
        with (
            zipfile.ZipFile(path) as archive,
            archive.open("ASAP_2_Final_github_train.csv") as member,
            io.TextIOWrapper(member, encoding="utf-8-sig", newline="") as f,
        ):
            yield from human_essays(csv.DictReader(f), dataset.id)
    elif dataset.id in {"ellipse", "persuade"}:
        with path.open(encoding="utf-8-sig", newline="") as f:
            yield from human_essays(csv.DictReader(f), dataset.id)
    else:
        raise ValueError(f"No enabled loader for {dataset.id}")


def examples(datasets, cache):
    csv.field_size_limit(8 * 1024 * 1024)
    for dataset in datasets:
        for artifact in dataset.artifacts:
            for record in read_artifact(dataset, artifact, fetch(artifact, cache)):
                if record.label not in {0, 1} or not record.text.strip():
                    raise ValueError(f"Invalid record in {dataset.id}")
                if dataset.use == "eval" and record.split != "test":
                    raise ValueError(f"Eval-only dataset {dataset.id} in fit partition")
                yield record
