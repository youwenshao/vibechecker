from types import SimpleNamespace

import numpy as np
import pytest
from scipy.stats import binom
from vibechecker_eval.band_controls import ControlRows, calibrate_high_band, high_cutoff


def test_cutoff_keeps_ties_and_existing_cutoff():
    scores = [0] * 444 + [83] * 4
    cutoff, k = high_cutoff(scores, previous_high=12)
    assert binom.cdf(k, len(scores), 0.02) <= 0.05 < binom.cdf(k + 1, len(scores), 0.02)
    assert cutoff == 84
    assert np.sum(np.asarray(scores) >= cutoff) <= k
    assert high_cutoff(scores, previous_high=93)[0] == 93


def test_insufficient_or_unattainable_controls_do_not_disable_high_band():
    with pytest.raises(ValueError, match="Insufficient"):
        high_cutoff([0] * 100, previous_high=12)
    with pytest.raises(ValueError, match="unattainable"):
        high_cutoff([100] * 448, previous_high=12)


def test_calibrated_band_uses_only_independent_essay_fit_sources():
    # Replacing the reference-only sources with arbitrary scores has no effect.
    class Classifier:
        def predict_proba(self, x):
            return np.column_stack((1 - x[:, 0], x[:, 0]))

    point = SimpleNamespace(point=lambda value: value)
    stacker = SimpleNamespace(
        low_threshold=2, high_threshold=12, classifier=Classifier(), calibrators={"pooled": point}
    )
    indices = np.r_[[0.0] * 444, [0.83] * 4, np.nan, np.nan]
    controls = ControlRows(
        np.asarray(["asap"] * 224 + ["ellipse"] * 224 + ["persuade", "raid"]),
        np.full(len(indices), 300),
        indices[:, None],
        np.empty((len(indices), 0)),
        {},
    )
    report = calibrate_high_band(stacker, None, controls)
    assert (stacker.low_threshold, stacker.high_threshold) == (2, 84)
    assert report["fit_by_source"]["ellipse"] == {"n": 224, "before": 4, "after": 0}
    assert report["n"] == 448
