"""Reserve and score Phase 1 essay splits for the sentence lens, without changing the model."""

import argparse
import gzip
import json
import os
import sqlite3
from pathlib import Path

from vibechecker_engine.deep import DeepModel, PairExtractor, weight_manifest
from vibechecker_engine.text import prepare, validate

from .loaders import examples, fingerprint
from .phase11 import MODEL_SHA
from .registry import registry, select, sha256


def reserve(features, excluded):
    db = sqlite3.connect(features.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        strata = json.loads(dict(db.execute("select key,value from meta"))["strata"])
        partitions = [[], []]
        groups = set()
        for key, source, fold, tags in db.execute(
            "select id,group_id,role,strata from documents where role in (1,2) "
            "and label=0 and features is not null order by id"
        ):
            if key in excluded or "genre/essay" not in {strata[t] for t in json.loads(tags)}:
                continue
            if source in groups:
                raise ValueError("Repeated source in essay folds")
            groups.add(source)
            partitions[fold - 1].append(key)
        return {"calibration": partitions[0][:160], "validation": partitions[1]}
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("features", "historical", "prospective", "cache", "out"):
        p.add_argument("--" + arg, type=Path, required=True)
    args = p.parse_args()
    receipts = Path("eval/reports/phase-1")
    expected = json.loads((receipts / "academic-addition-input.json").read_bytes())["file_sha256"][
        "base_features"
    ]
    traces = json.loads((receipts / "phase-1.1/metrics.json").read_bytes())["trace_sha256"]
    if (
        sha256(args.features) != expected
        or [sha256(p) for p in (args.historical, args.prospective)] != traces
    ):
        raise ValueError("Unexpected Phase 1.1 inputs")
    excluded = set()
    for path in (args.historical, args.prospective):
        excluded.update(json.loads(path.read_bytes())["scores"])
    plan = reserve(args.features, excluded)
    args.out.mkdir(parents=True, exist_ok=True)
    membership = args.out / "membership.json"
    serialized = json.dumps(plan, sort_keys=True)
    if membership.exists() and membership.read_text() != serialized:
        raise ValueError("Reserved essay membership changed")
    membership.write_text(serialized)
    keys = set(plan["calibration"] + plan["validation"])
    texts = {
        key: item.text
        for item in examples(select(registry(), ["asap", "ellipse", "liang"]), args.cache)
        if not item.label and (key := fingerprint(item.text)) in keys
    }
    if keys != texts.keys():
        raise ValueError("Incomplete reserved corpus")
    model_path = Path(os.environ["VIBECHECKER_DEEP_MODEL"])
    if sha256(model_path) != MODEL_SHA:
        raise ValueError("Unexpected Deep model")
    model = DeepModel.load(model_path)
    if weight_manifest() != model.identity:
        raise ValueError("Unexpected model weights")
    pair = PairExtractor.from_env()
    if pair.backend.name != "mlx-metal":
        raise ValueError("The pinned essay reference uses Metal")
    result = {"model_sha256": MODEL_SHA, "membership_sha256": sha256(membership), "folds": {}}
    for fold, ids in plan.items():
        scores = []
        for i, key in enumerate(ids):
            doc = prepare(texts[key])
            validate(doc, "deep")
            values = [model.heads.sentence.score(w) for _, waves in pair.chunks(doc) for w in waves]
            if len(values) != len(doc.sentences):
                raise ValueError("Sentence alignment differs")
            scores.extend(values)
            if (i + 1) % 40 == 0:
                print(f"{fold}: {i + 1}/{len(ids)} essays", flush=True)
        result["folds"][fold] = {"documents": len(ids), "scores": scores}
    with (
        (args.out / "essay-sentences.json.gz").open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as archive,
    ):
        archive.write(json.dumps(result).encode("utf8"))


if __name__ == "__main__":
    main()
