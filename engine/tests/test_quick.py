from types import SimpleNamespace

import numpy as np
import pytest
from vibechecker_engine import FEATURE_NAMES, FeatureExtractor, QuickEngine, QuickStacker
from vibechecker_engine.backends.base import TokenStats
from vibechecker_engine.text import WORD, Refusal


class LM:
    name = "mlx-cpu"

    def token_stats(self, ids):
        n = len(ids) - 1
        return TokenStats(-np.ones(n) * np.log(4), np.full(n, 2), np.linspace(0.1, 1, n))


class Tokenizer:
    bos_token_id = 42

    def __call__(self, text, **kwargs):
        words = list(WORD.finditer(text))
        return {"input_ids": list(range(len(words))), "offset_mapping": [w.span() for w in words]}


def test_features_and_early_refusal():
    encoder = SimpleNamespace(score=lambda text: (0.25, [0.2, 0.3]))
    extractor = FeatureExtractor(LM(), Tokenizer(), encoder)
    text = "This is an essay about the history of our town. " * 45
    row = extractor.extract(text)
    np.testing.assert_allclose(row.values[:3], [4.0, 0.0, np.log(2)], atol=1e-12)
    assert row.values[4] == 0.25
    assert row.word_count == 450
    assert all(2 <= len(series) <= 16 for series in row.samples.values())
    with pytest.raises(Refusal, match="too_short"):
        FeatureExtractor(SimpleNamespace(name="mlx-cpu"), None, None).extract("I walked.")


def test_fit_predict_roundtrip(tmp_path):
    rng = np.random.default_rng(64)
    train = rng.normal(size=(150, len(FEATURE_NAMES)))
    cal = rng.normal(size=(100, len(FEATURE_NAMES)))
    labels = (train[:, 4] > 0).astype(int)
    truth = (cal[:, 4] > 0).astype(int)
    model = QuickStacker.fit(train, labels, cal, truth, [150] * len(cal))
    assert set(model.calibrators) == {"pooled"}
    assert len(model.calibrators["pooled"].bootstrap) == 200
    assert 0 <= model.low_threshold <= model.high_threshold <= 101
    example = model.predict(cal[0], 299)
    assert example["interval"]["low"] <= example["index"] <= example["interval"]["high"]
    assert example["interval"]["high"] - example["interval"]["low"] >= 20
    assert example["signals"][2]["humanReference"] == np.median(train[labels == 0, 4])
    path = tmp_path / "published.joblib"
    model.save(path)
    assert QuickStacker.load(path).predict(cal[0], 299) == example
    row = SimpleNamespace(
        values=cal[0], word_count=299, flags=("invisible",), samples={"e1": [1.2, 1.3]}
    )
    engine = QuickEngine(SimpleNamespace(backend="mlx-cpu", extract=lambda text: row), model)
    result = engine.analyze("only for this injected fixture")
    assert result["wordCount"] == 299 and result["signals"][0]["samples"] == [1.2, 1.3]
    assert result["flags"] == ["invisible"]


def test_one_class_calibration_rejected():
    with pytest.raises(ValueError, match="human and machine"):
        QuickStacker.fit(
            [[0] * len(FEATURE_NAMES)] * 2,
            [0, 1],
            [[0] * len(FEATURE_NAMES)] * 2,
            [0, 0],
            [200, 200],
        )


def test_balanced_reference_prior_and_stratum_threshold():
    # A classifier with no information should give the reference prior even
    # when only one tenth of the calibration set is machine-written.
    row = [0.0] * len(FEATURE_NAMES)
    model = QuickStacker.fit(
        [row] * 20,
        [0, 1] * 10,
        [row] * 1010,
        [0] * 900 + [1] * 100 + [0, 1] * 5,
        [170] * 1000 + [700] * 10,
    )
    assert set(model.calibrators) == {"pooled", "150-299"}
    for length in (170, 700):
        result = model.predict(row, length)
        assert result["index"] == 50
        assert result["band"] == "low"
