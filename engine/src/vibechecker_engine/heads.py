"""Learned Deep heads. Fit only on labeled, training-partition features."""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

CHANNELS = 4


def _labels(y):
    labels = np.asarray(y)
    if labels.ndim != 1 or set(labels.tolist()) != {0, 1}:
        raise ValueError("The head needs labeled examples of both classes")
    return labels.astype(int)


@dataclass
class SentenceHead:
    """One learned attention weight per token, followed by a binary readout."""

    scale: StandardScaler
    query: np.ndarray
    readout: np.ndarray
    bias: float

    @classmethod
    def fit(cls, waveforms, labels):
        if len(waveforms) != len(labels):
            raise ValueError("One label per sentence required")
        rows = [(w, y) for w, y in zip(waveforms, labels, strict=True) if len(w)]
        y = _labels([label for _, label in rows])
        sizes = np.array([len(w) for w, _ in rows])
        values = np.vstack([w for w, _ in rows])
        if values.shape != (sizes.sum(), CHANNELS) or not np.isfinite(values).all():
            raise ValueError("Invalid training waveform")
        scaler = StandardScaler().fit(values)
        x = np.clip(scaler.transform(values).astype(float), -12, 12)
        starts = sizes.cumsum() - sizes
        group = np.repeat(np.arange(len(y)), sizes)
        weights = 0.5 / np.bincount(y)[y]

        def objective(params):
            query, readout, bias = params[:CHANNELS], params[CHANNELS:-1], params[-1]
            attention = x @ query
            attention = np.exp(attention - np.maximum.reduceat(attention, starts)[group])
            attention /= np.add.reduceat(attention, starts)[group]
            pooled = np.add.reduceat(x * attention[:, None], starts, axis=0)
            logit = pooled @ readout + bias
            loss = weights @ (np.logaddexp(0, logit) - y * logit)
            residual = weights * (expit(logit) - y)
            # d(softmax pooling)/d(query) is a weighted covariance.
            token_weight = residual[group] * attention * ((x @ readout) - (pooled @ readout)[group])
            grad = np.r_[token_weight @ x, residual @ pooled, residual.sum()]
            reg = 0.001
            loss += reg * (params[:-1] @ params[:-1]) / 2
            grad[:-1] += reg * params[:-1]
            return loss, grad

        fit = minimize(objective, np.zeros(2 * CHANNELS + 1), jac=True, method="L-BFGS-B")
        if not np.isfinite(fit.fun) or not np.isfinite(fit.x).all():
            raise ValueError("Sentence head fitting failed")
        return cls(scaler, fit.x[:CHANNELS], fit.x[CHANNELS:-1], float(fit.x[-1]))

    def score(self, waveform):
        if not len(waveform):
            return 0.5
        x = np.clip(self.scale.transform(waveform), -12, 12)
        logits = x @ self.query
        weights = np.exp(logits - logits.max())
        return float(expit(np.average(x, axis=0, weights=weights) @ self.readout + self.bias))


def _classifier(x, y, seed):
    labels = _labels(y)
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", random_state=seed, max_iter=500),
    ).fit(x, labels)


def _probability(classifier, values):
    return float(classifier.predict_proba([values])[0, 1])


@dataclass
class DeepHeads:
    sentence: SentenceHead
    ghost: object
    esl: object
    laundering: object
    discrepancy_threshold: float
    binoculars_threshold: float

    @classmethod
    def fit(
        cls,
        waveforms,
        sentence_labels,
        ghost_x,
        doc_labels,
        esl_x,
        esl_y,
        laundering_x,
        laundering_y,
        *,
        seed=42,
    ):
        sentence = SentenceHead.fit(waveforms, sentence_labels)
        human = [w for w, y in zip(waveforms, sentence_labels, strict=True) if y == 0 and len(w)]
        reference = np.array([waveform_signals(w) for w in human])
        return cls(
            sentence,
            _classifier(ghost_x, doc_labels, seed),
            _classifier(esl_x, esl_y, seed),
            _classifier(laundering_x, laundering_y, seed),
            float(np.quantile(reference[:, 0], 0.90)),
            float(np.quantile(reference[:, 1], 0.10)),
        )

    def sentence_item(self, sentence, waveform):
        score = self.sentence.score(waveform)
        signals = []
        if len(waveform):
            e3, e4 = waveform_signals(waveform)
            if e3 > self.discrepancy_threshold:
                signals.append("e3")
            if e4 < self.binoculars_threshold:
                signals.append("e4")
            if score >= 0.5:
                signals.append("e5")
        return {
            "start": sentence.start_utf16,
            "end": sentence.end_utf16,
            "score": score,
            "signals": signals,
        }

    def sentence_scores(self, raw):
        return np.array([self.sentence.score(w) for w in raw.waveforms])

    def features(self, raw, sentence_scores=None):
        scores = self.sentence_scores(raw) if sentence_scores is None else sentence_scores
        mean = np.average(scores, weights=[len(w) for w in raw.waveforms])
        return (*raw.quick.values, raw.e3, raw.e4, float(mean), _probability(self.ghost, raw.ghost))

    def flags(self, raw):
        flags = list(raw.quick.flags)
        if _probability(self.esl, raw.flag_features) >= 0.5:
            flags.append("esl")
        if _probability(self.laundering, raw.flag_features) >= 0.5:
            flags.append("laundering")
        return flags


def waveform_signals(wave):
    """Sentence-local E3 and E4 contributions at observed-token positions."""
    logp, cross, sd, _ = wave.astype(float).T
    deviation = np.linalg.norm(sd)
    e3 = (logp - cross).sum() / deviation if deviation else 0.0
    e4 = logp.mean() / cross.mean() if cross.mean() else 1.0
    return e3, e4
