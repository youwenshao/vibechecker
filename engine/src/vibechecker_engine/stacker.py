"""A separately trained stacker and held-out, balanced-prior calibration set."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import joblib
import numpy as np
from scipy.special import expit, logit
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from threadpoolctl import threadpool_limits

from .signals import DISPLAY_FEATURES, FEATURE_NAMES

MIN_WIDTH = {"150-299": 20, "300-599": 14, "600-1199": 10, "1200+": 8}


def length_bin(n):
    for end, key in ((300, "150-299"), (600, "300-599"), (1200, "600-1199")):
        if n < end:
            return key
    return "1200+"


@dataclass
class Curve:
    x: np.ndarray
    y: np.ndarray

    def __call__(self, scores):
        return np.interp(scores, self.x, self.y)

    @classmethod
    def fit(cls, scores, labels):
        # Reweight *after* drawing a bootstrap sample. The estimated probability
        # should always refer to the documented 50% reference prior.
        weight = 0.5 / np.bincount(labels)[labels]
        fit = IsotonicRegression(out_of_bounds="clip").fit(scores, labels, sample_weight=weight)
        return cls(fit.X_thresholds_, fit.y_thresholds_)


@dataclass
class Calibration:
    point: Curve
    bootstrap: list[Curve]

    @classmethod
    def fit(cls, scores, labels, rng):
        human = np.flatnonzero(labels == 0)
        machine = np.flatnonzero(labels == 1)
        curves = []
        for _ in range(200):
            sample = np.r_[rng.choice(human, len(human)), rng.choice(machine, len(machine))]
            curves.append(Curve.fit(scores[sample], labels[sample]))
        return cls(Curve.fit(scores, labels), curves)


def _arrays(x, y, feature_names):
    matrix = np.asarray(x, dtype=float)
    labels = np.asarray(y)
    if matrix.shape != (len(labels), len(feature_names)) or not np.isfinite(matrix).all():
        raise ValueError("Expected one complete finite feature vector per label")
    if labels.ndim != 1 or set(labels.tolist()) != {0, 1}:
        raise ValueError("Training and calibration each require human and machine examples")
    return matrix, labels.astype(int)


def _band_threshold(human_indices, fpr):
    # Rounding and ties affect the displayed bands. Never classify a tie block
    # as high if that would exceed the empirical FPR limit. 101 disables a band.
    return next(t for t in range(102) if np.mean(human_indices >= t) <= fpr)


@dataclass
class ProbeAnchoredClassifier:
    """Keep a fixed positive contribution from the independently trained probe."""

    estimator: HistGradientBoostingClassifier
    probe_weight: float

    def predict_proba(self, matrix):
        # ProbeDeepStacker reserves the final feature for the supervised probe probability.
        margin = self.estimator.decision_function(matrix)
        probe_margin = logit(np.clip(np.asarray(matrix)[:, -1], 1e-7, 1 - 1e-7))
        positive = expit((1 - self.probe_weight) * margin + self.probe_weight * probe_margin)
        return np.column_stack((1 - positive, positive))


@dataclass
class QuickStacker:
    classifier: HistGradientBoostingClassifier | ProbeAnchoredClassifier
    calibrators: dict[str, Calibration]
    human_reference: np.ndarray
    low_threshold: int
    high_threshold: int
    feature_names: tuple[str, ...] = FEATURE_NAMES

    FEATURES: ClassVar = FEATURE_NAMES
    DISPLAY: ClassVar = DISPLAY_FEATURES
    MONOTONIC: ClassVar = {"encoder_probability": 1}

    @classmethod
    def fit(
        cls,
        train_x,
        train_y,
        cal_x,
        cal_y,
        cal_word_counts,
        *,
        seed=42,
        max_leaf_nodes=31,
        l2_regularization=0.0,
        probe_anchor=0.0,
    ):
        train, labels = _arrays(train_x, train_y, cls.FEATURES)
        calibration, truth = _arrays(cal_x, cal_y, cls.FEATURES)
        if len(cal_word_counts) != len(truth):
            raise ValueError("Calibration word counts must match the calibration rows")
        constraints = [cls.MONOTONIC.get(name, 0) for name in cls.FEATURES]
        if not 0 <= probe_anchor < 1 or (
            probe_anchor and cls.FEATURES[-1] != "frozen_encoder_probe"
        ):
            raise ValueError("Anchoring requires an appended fitted probe and weight in [0, 1)")
        model = HistGradientBoostingClassifier(
            monotonic_cst=constraints,
            random_state=seed,
            max_leaf_nodes=max_leaf_nodes,
            l2_regularization=l2_regularization,
            early_stopping=False,
            min_samples_leaf=max(2, min(20, len(labels) // 12)),
        )
        with threadpool_limits(limits=1, user_api="openmp"):
            model.fit(train, labels)
            if probe_anchor:
                model = ProbeAnchoredClassifier(model, probe_anchor)
            raw = model.predict_proba(calibration)[:, 1]

        rng = np.random.default_rng(seed)
        pooled = Calibration.fit(raw, truth, rng)
        calibrators = {"pooled": pooled}
        points = pooled.point(raw)
        strata = np.asarray([length_bin(n) for n in cal_word_counts])
        for stratum in np.unique(strata):
            keep = strata == stratum
            if keep.sum() >= 1000 and len(np.unique(truth[keep])) == 2:
                group = Calibration.fit(raw[keep], truth[keep], rng)
                calibrators[stratum] = group
                points[keep] = group.point(raw[keep])
        human = np.rint(points[truth == 0] * 100)
        return cls(
            model,
            calibrators,
            np.median(train[labels == 0], axis=0),
            _band_threshold(human, 0.20),
            _band_threshold(human, 0.02),
            cls.FEATURES,
        )

    def predict(self, values, word_count):
        vector = np.asarray(values, dtype=float)
        if vector.shape != (len(self.feature_names),) or not np.isfinite(vector).all():
            raise ValueError("Expected a complete finite feature vector")
        with threadpool_limits(limits=1, user_api="openmp"):
            raw = self.classifier.predict_proba(vector.reshape(1, -1))[0, 1]
        stratum = length_bin(word_count)
        group = self.calibrators.get(stratum, self.calibrators["pooled"])
        index = int(np.rint(100 * group.point(raw)))
        bootstrap = [100 * curve(raw) for curve in group.bootstrap]
        low, high = np.percentile(bootstrap, [5, 95])
        low, high = min(low, index), max(high, index)
        width = MIN_WIDTH[stratum]
        if high - low < width:
            low = float(np.clip((low + high - width) / 2, 0, 100 - width))
            high = low + width
        band = "low" if index < self.low_threshold else "mixed"
        if index >= self.high_threshold:
            band = "high"
        return {
            "index": index,
            "interval": {"low": int(np.floor(low)), "high": int(np.ceil(high))},
            "band": band,
            "signals": [
                {
                    "id": key,
                    "value": float(vector[col]),
                    "humanReference": float(self.human_reference[col]),
                }
                for key, col in self.DISPLAY.items()
            ],
        }

    def save(self, path):
        save_artifact(self, path)

    @classmethod
    def load(cls, path):
        # Only deployment-controlled artifacts should be passed to joblib.
        instance = joblib.load(path)
        if not isinstance(instance, cls) or instance.feature_names != cls.FEATURES:
            raise ValueError("Incompatible Quick stacker")
        return instance


def save_artifact(artifact, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        joblib.dump(artifact, tmp_path, compress=3)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)
