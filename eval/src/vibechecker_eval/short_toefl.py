"""Measure the frozen Deep index on the pinned short TOEFL corpus, offline only."""

import argparse
import os
from collections import Counter
from pathlib import Path
from time import perf_counter

from vibechecker_engine.deep import DeepEngine
from vibechecker_engine.text import Refusal, prepare, validate

from .deep_runner import write_json
from .loaders import examples, fingerprint
from .metrics import length_bin, rate
from .registry import registry, sha256


def short_index(engine, doc):
    """Use the same waveforms, probe and document predictor as DeepEngine.stream."""
    if not 0 < doc.word_count < 300:
        raise ValueError("Expected a short research passage")
    parts, waves = [], []
    for stats, chunk_waves in engine.extractor.pair.chunks(doc):
        parts.append(stats)
        waves.extend(chunk_waves)
    raw = engine.extractor.aggregate(
        doc, parts, waves, include_encoder_evidence=engine.model.probe is not None
    )
    return engine.model.stacker.predict(engine.model.features(raw), doc.word_count)["index"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start = perf_counter()
    if sha256(Path(os.environ["VIBECHECKER_DEEP_MODEL"])) != args.model_sha256:
        raise ValueError("Unexpected frozen artifact")
    engine = DeepEngine.from_env()
    dataset = registry()["liang"]
    members = [r for r in examples([dataset], args.cache) if r.dataset == "liang/toefl"]
    if len(members) != 91:
        raise ValueError("Expected all 91 pinned TOEFL records")
    rows = []
    refusals = Counter()
    for number, item in enumerate(members, 1):
        doc = prepare(item.text)
        try:
            validate(doc, "deep")
        except Refusal as exc:
            refusals[exc.code] += 1
        else:
            raise ValueError("Unexpected product admission")
        rows.append(
            {
                "row": number,
                "id": fingerprint(item.text),
                "words": doc.word_count,
                "index": short_index(engine, doc),
            }
        )
    cutoff = engine.model.stacker.high_threshold
    groups = {}
    for group in ["all", *sorted({length_bin(r["words"]) for r in rows})]:
        selected = [r for r in rows if group == "all" or length_bin(r["words"]) == group]
        groups[group] = rate(sum(r["index"] >= cutoff for r in selected), len(selected))
    write_json(
        {
            "backend": engine.backend,
            "model_sha256": args.model_sha256,
            "quick_prefill": engine.extractor.quick.lm.chunk_size,
            "corpus_sha256": next(a.sha256 for a in dataset.artifacts if a.name == "toefl"),
            "product_refusals": dict(refusals),
            "cutoff": cutoff,
            "groups": groups,
            "elapsed_seconds": perf_counter() - start,
            "scores": rows,
        },
        args.out,
    )


if __name__ == "__main__":
    main()
