from dataclasses import replace

import numpy as np
import pytest
from vibechecker_engine.backends.pair import PairStats, binoculars, fast_detect_gpt
from vibechecker_engine.deep import (
    MODEL_KEYS,
    DeepEngine,
    DeepExtractor,
    DeepHeads,
    DeepModel,
    DeepStacker,
    PairExtractor,
    check_tokenizers,
    weight_manifest,
)
from vibechecker_engine.signals import FeatureRow
from vibechecker_engine.text import WORD, Refusal, prepare


def reduce_pair(observer, performer, ids, start, stop, pad_id):
    """Independent dense CPU oracle for the lazy MLX backend."""
    from scipy.special import log_softmax, softmax

    a = log_softmax(performer[start:stop], axis=-1)
    b = log_softmax(observer[start:stop], axis=-1)
    p = softmax(observer[start:stop], axis=-1)
    targets = ids[start + 1 : min(stop + 1, len(ids))]
    idx = np.arange(len(targets))
    cross = (p * a).sum(-1)
    return PairStats(
        a[idx, targets],
        cross[: len(idx)],
        (p * a**2).sum(-1)[: len(idx)],
        b[idx, targets],
        cross[np.array(ids[start:stop]) != pad_id],
    )


def test_published_implementation_goldens():
    # Evaluated with PyTorch fp32 and the authors' actual functions at the
    # immutable revisions cited in engine/README.md. The interior ID 0 and
    # distinct final row exercise both masking and reference/performer roles.
    t = np.arange(24).reshape(6, 4)
    ids = [1, 3, 0, 2, 1, 3]
    stats = reduce_pair(2 * np.sin(t / 3), 3 * np.cos(t / 5), ids, 0, len(ids), 0)
    assert binoculars(stats) == pytest.approx(0.9809965, abs=3e-7)
    assert fast_detect_gpt(stats) == pytest.approx(-0.01978410594, abs=3e-6)


class CPUPair:
    name = "mlx-cpu"

    def __init__(self):
        self.calls = []

    def caches(self):
        return [0]

    def pair_stats(self, ids, start, stop, caches, pad_id):
        assert caches[0] == start
        caches[0] = stop
        self.calls.append((start, stop))
        t = np.arange(len(ids) * 7).reshape(len(ids), 7)
        return reduce_pair(np.sin(t / 3), np.cos(t / 5), ids, start, stop, pad_id)


class Tokenizer:
    pad_token_id = None
    eos_token_id = 6

    def __call__(self, text, **kwargs):
        matches = list(WORD.finditer(text))
        return {
            "input_ids": [len(m.group()) % 6 for m in matches],
            "offset_mapping": [m.span() for m in matches],
        }


TEST_IDENTITY = {key: {"model.safetensors": "a" * 64} for key in MODEL_KEYS}


class Quick:
    backend = "mlx-cpu"

    def extract_prepared(self, doc):
        return FeatureRow(tuple(np.arange(9, dtype=float)), doc.word_count, doc.flags, {})


def train_model(raw):
    rng = np.random.default_rng(319)
    labels = np.array([0, 1] * 20)
    waveforms = [rng.normal(size=(8, 4)) + np.array([label * 2, -3, 2, 0]) for label in labels]
    ghost = rng.normal(size=(40, len(raw.ghost))) + labels[:, None]
    flags = rng.normal(size=(40, len(raw.flag_features))) + labels[:, None]
    heads = DeepHeads.fit(waveforms, labels, ghost, labels, flags, labels, flags, labels)
    columns = len(heads.features(raw))
    train, cal = [rng.normal(size=(40, columns)) + labels[:, None] for _ in range(2)]
    return DeepModel(heads, DeepStacker.fit(train, labels, cal, labels, [350] * 40), TEST_IDENTITY)


def test_progressive_batches_match_unchunked_and_batch_inference(tmp_path):
    text = "😀 We looked for a good café in our town.\r\n" + (
        "We read the very same book about new houses near our school. " * 36
    )
    doc = prepare(text)
    backend = CPUPair()
    pair = PairExtractor(backend, Tokenizer())
    extractor = DeepExtractor(Quick(), pair, TEST_IDENTITY)
    raw = extractor.extract(text)
    e3, e4 = pair.score(doc.normalized)
    assert (raw.e3, raw.e4) == pytest.approx((e3, e4))
    model = train_model(raw)
    artifact = tmp_path / "deep.joblib"
    model.save(artifact)
    engine = DeepEngine(extractor, DeepModel.load(artifact))
    backend.calls.clear()
    stream = engine.stream(doc)
    first = next(stream)
    assert first["type"] == "sentences" and len(backend.calls) == 1
    assert len(first["items"]) < len(doc.sentences)
    assert first["items"][0]["end"] == doc.sentences[0].end_utf16
    events = [first, *stream]
    assert events[-1]["type"] == "result"
    result = events[-1]["result"]
    assert result["sentences"] == [
        s for e in events if e["type"] == "sentences" for s in e["items"]
    ]
    assert {s["id"] for s in result["signals"]} == {*(f"e{i}" for i in range(1, 8)), "stylometry"}
    assert len(result["sentences"]) == len(doc.sentences)
    assert engine.analyze(text) == result
    folded = list(engine.stream(replace(doc, chunks=(doc.sentences,))))[-1]["result"]
    assert folded == result
    with pytest.raises(Refusal, match="too_short"):
        engine.analyze("One short sentence.")


def test_esl_caution_widens_only_the_interval():
    class Constant:
        def __init__(self, p):
            self.p = p

        def predict_proba(self, x):
            return np.repeat([[1 - self.p, self.p]], len(x), axis=0)

    text = "Many of the people in my town travel to work by bus. " * 25
    extractor = DeepExtractor(Quick(), PairExtractor(CPUPair(), Tokenizer()), TEST_IDENTITY)
    model = train_model(extractor.extract(text))
    engine = DeepEngine(extractor, model)
    model.heads.esl = Constant(0)
    ordinary = engine.analyze(text)
    model.heads.esl = Constant(1)
    cautious = engine.analyze(text)
    assert set(cautious["flags"]) - set(ordinary["flags"]) == {"esl"}
    assert (cautious["index"], cautious["band"]) == (ordinary["index"], ordinary["band"])
    assert cautious["interval"]["low"] <= ordinary["interval"]["low"]
    assert cautious["interval"]["high"] >= ordinary["interval"]["high"]


def test_pair_requires_same_normalization_merges_and_special_insertion():
    import json
    from types import SimpleNamespace

    def tokenizer(spec):
        return SimpleNamespace(
            is_fast=True, backend_tokenizer=SimpleNamespace(to_str=lambda: json.dumps(spec))
        )

    first = {
        "normalizer": None,
        "model": {"vocab": {"a": 0}, "merges": []},
        "added_tokens": [],
        "post_processor": None,
    }
    check_tokenizers(tokenizer(first), tokenizer(dict(first)))
    for difference in (
        {"normalizer": {"type": "NFKC"}},
        {"model": {**first["model"], "merges": ["a a"]}},
        {"post_processor": {"type": "TemplateProcessing", "single": ["BOS", "A"]}},
        {"added_tokens": [{"content": "extra", "id": 1}]},
    ):
        with pytest.raises(ValueError, match="tokenization"):
            check_tokenizers(tokenizer(first), tokenizer(first | difference))


def test_reject_changed_weights_before_serving(tmp_path, monkeypatch):
    from types import SimpleNamespace

    for key in MODEL_KEYS:
        path = tmp_path / key
        path.mkdir()
        (path / "model.safetensors").write_bytes(key.encode())
        (path / "config.json").write_bytes(b"{}")
        monkeypatch.setenv("VIBECHECKER_" + key, str(path))
    received = weight_manifest()
    assert all(len(v["model.safetensors"]) == 64 for v in received.values())
    model = DeepModel(None, None, received)
    model.verify(SimpleNamespace(identity=weight_manifest()))
    (tmp_path / "PAIR_PERFORMER" / "model.safetensors").write_bytes(b"different")
    with pytest.raises(ValueError, match="different checkpoint"):
        DeepEngine(SimpleNamespace(identity=weight_manifest()), model)
