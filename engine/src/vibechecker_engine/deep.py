"""Progressive Deep scoring. Training and serving share the same feature extraction."""

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import joblib
import numpy as np

from .backends.base import PairBackend, PairStats
from .backends.pair import MLXPairBackend, binoculars, fast_detect_gpt
from .heads import DeepHeads, waveform_signals
from .signals import (
    DISPLAY_FEATURES,
    ENCODER_VECTOR_VERSION,
    FEATURE_NAMES,
    FeatureExtractor,
    FeatureRow,
    _samples,
)
from .stacker import QuickStacker, save_artifact
from .text import Prepared, prepare, validate

DEEP_FEATURE_NAMES = (
    *FEATURE_NAMES,
    "fast_detect_gpt",
    "binoculars",
    "sentence_head",
    "ghostbuster",
)


class DeepStacker(QuickStacker):
    FEATURES = DEEP_FEATURE_NAMES
    DISPLAY: ClassVar = {**DISPLAY_FEATURES, "e3": 9, "e4": 10, "e5": 11, "e7": 12}
    MONOTONIC: ClassVar = {
        **QuickStacker.MONOTONIC,
        "fast_detect_gpt": 1,
        "binoculars": -1,
        "sentence_head": 1,
        "ghostbuster": 1,
    }


class ProbeDeepStacker(DeepStacker):
    FEATURES = (*DEEP_FEATURE_NAMES, "frozen_encoder_probe")
    MONOTONIC: ClassVar = {**DeepStacker.MONOTONIC, "frozen_encoder_probe": 1}


def probe_features(heads, probe, raw, sentence_scores=None):
    features = heads.features(raw, sentence_scores)
    if probe is None:
        return features
    vector = raw.encoder_vector
    if vector is None or vector.ndim != 1 or not np.isfinite(vector).all():
        raise ValueError("The fitted probe requires a finite frozen encoder representation")
    probability = float(probe.predict_proba(vector[None, :])[0, 1])
    if not 0 <= probability <= 1:
        raise ValueError("The frozen encoder probe produced an invalid probability")
    return (*features, probability)


def check_tokenizers(observer, performer):
    if not observer.is_fast or not performer.is_fast:
        raise ValueError("Deep requires fast tokenizers with character offsets")
    # A vocabulary alone does not define the token sequence. Comparing the
    # actual normalizer, merge rules, added-token behavior and postprocessor
    # also covers BOS/EOS insertion. Chat templates are unused for raw essays.
    keys = ("model", "normalizer", "pre_tokenizer", "post_processor", "added_tokens")
    first, second = [json.loads(t.backend_tokenizer.to_str()) for t in (observer, performer)]
    if any(first.get(key) != second.get(key) for key in keys):
        raise ValueError("Observer and performer must share the raw tokenization pipeline")


MODEL_KEYS = ("LM", "ENCODER", "PAIR_OBSERVER", "PAIR_PERFORMER")


def weight_manifest():
    manifest = {}
    for name in MODEL_KEYS:
        directory = Path(os.environ["VIBECHECKER_" + name])
        files = sorted(directory.glob("*.safetensors"))
        if not files:
            raise ValueError(f"No safetensors weights for {name}")
        files.extend(
            f
            for f in sorted(directory.iterdir())
            if f.is_file() and f.suffix in {".json", ".model", ".txt", ".jinja"}
        )
        hashes = {}
        for f in files:
            with f.open("rb") as stream:
                hashes[f.name] = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest[name] = hashes
    return manifest


class PairExtractor:
    def __init__(self, backend: PairBackend, tokenizer):
        self.backend, self.tokenizer = backend, tokenizer
        self.pad_id = tokenizer.pad_token_id
        if self.pad_id is None:
            self.pad_id = tokenizer.eos_token_id

    @classmethod
    def from_env(cls):
        from transformers import AutoTokenizer

        paths = [
            Path(os.environ[key])
            for key in ("VIBECHECKER_PAIR_OBSERVER", "VIBECHECKER_PAIR_PERFORMER")
        ]
        tokenizer, other = [
            AutoTokenizer.from_pretrained(p, use_fast=True, local_files_only=True) for p in paths
        ]
        check_tokenizers(tokenizer, other)
        backend = MLXPairBackend.from_paths(*paths, requested=os.getenv("VIBECHECKER_BACKEND"))
        return cls(backend, tokenizer)

    def score(self, text, max_tokens=512):
        # The published reference run uses the raw passage and 512-token truncation.
        encoded = self.tokenizer(text, max_length=max_tokens, truncation=True, verbose=False)
        ids = encoded["input_ids"]
        if len(ids) < 2:
            raise ValueError("At least two tokens required")
        stats = self.backend.pair_stats(ids, 0, len(ids), self.backend.caches(), self.pad_id)
        return fast_detect_gpt(stats), binoculars(stats)

    def chunks(self, doc):
        encoded = self.tokenizer(doc.normalized, return_offsets_mapping=True, verbose=False)
        ids, offsets = encoded["input_ids"], encoded["offset_mapping"]
        if len(ids) < 2:
            raise ValueError("At least two tokens required")
        # Tokenize once. A byte-level token that includes preceding whitespace
        # belongs to the sentence containing its final character.
        ends = np.asarray([s.norm_end for s in doc.sentences])
        positions = np.maximum(0, np.asarray(offsets)[1:, 1] - 1)
        groups = np.searchsorted(ends, positions, side="right").clip(max=len(ends) - 1)
        # Some tokenizers use (0, 0) for an automatically added terminal special.
        groups = np.maximum.accumulate(groups)
        caches = self.backend.caches()
        sentence_start = context_start = 0
        for chunk in doc.chunks:
            sentence_stop = sentence_start + len(chunk)
            target_stop = int(np.searchsorted(groups, sentence_stop))
            # The official Binoculars denominator needs logits even at the last
            # input position, where we have no observed next-token target.
            context_stop = len(ids) if sentence_stop == len(ends) else target_stop
            stats = self.backend.pair_stats(ids, context_start, context_stop, caches, self.pad_id)
            deviation = np.sqrt(np.maximum(stats.cross_sq - stats.cross.astype(float) ** 2, 0))
            wave = np.column_stack((stats.logp_a, stats.cross, deviation, stats.logp_b)).astype(
                np.float32
            )
            boundaries = np.searchsorted(
                groups[context_start:target_stop], np.arange(sentence_start + 1, sentence_stop)
            )
            yield stats, tuple(np.split(wave, boundaries))
            context_start, sentence_start = context_stop, sentence_stop


@dataclass
class DeepDocument:
    quick: FeatureRow
    waveforms: tuple[np.ndarray, ...]
    e3: float
    e4: float
    ghost: tuple[float, ...]
    flag_features: tuple[float, ...]

    @property
    def encoder_vector(self):
        return self.quick.encoder_vector


class DeepExtractor:
    def __init__(self, quick, pair, identity, *, include_encoder_evidence=False):
        if quick.backend != pair.backend.name:
            raise ValueError("Quick and pair models must be on the same backend")
        self.quick, self.pair, self.backend = quick, pair, quick.backend
        self.identity = identity
        self.include_encoder_evidence = include_encoder_evidence

    @classmethod
    def from_env(cls, quick_extractor=None, *, include_encoder_evidence=False):
        return cls(
            quick_extractor or FeatureExtractor.from_env(),
            PairExtractor.from_env(),
            weight_manifest(),
            include_encoder_evidence=include_encoder_evidence,
        )

    def aggregate(self, doc, parts, waveforms, *, include_encoder_evidence=None):
        if include_encoder_evidence is None:
            include_encoder_evidence = self.include_encoder_evidence
        quick = (
            self.quick.extract_prepared(doc, include_encoder_evidence=True)
            if include_encoder_evidence
            else self.quick.extract_prepared(doc)
        )
        stats = PairStats.concatenate(parts)
        e3, e4 = fast_detect_gpt(stats), binoculars(stats)
        # Ghostbuster-style vector operations on the two observed-token log
        # probabilities preserve agreement and spread beyond their means.
        a, b = stats.logp_a.astype(float), stats.logp_b.astype(float)
        delta = a - b
        ghost = (
            e3,
            e4,
            float(np.mean(delta)),
            float(np.std(delta)),
            float(np.mean(np.abs(delta))),
            float(np.mean(a > b)),
            float(np.mean((a - a.mean()) * (b - b.mean()))),
            *quick.values[:4],
        )
        flags = (
            *quick.values,
            *ghost[:7],
            float("invisible" in quick.flags),
            float("homoglyph" in quick.flags),
        )
        if not np.isfinite(ghost).all() or not np.isfinite(flags).all():
            raise ValueError("Nonfinite Deep features")
        return DeepDocument(quick, tuple(waveforms), e3, e4, ghost, flags)

    def extract(self, text):
        doc = prepare(text)
        validate(doc, "deep")
        parts, waveforms = [], []
        for stats, waves in self.pair.chunks(doc):
            parts.append(stats)
            waveforms.extend(waves)
        return self.aggregate(doc, parts, waveforms)


@dataclass
class DeepModel:
    heads: DeepHeads
    stacker: DeepStacker
    identity: dict[str, dict[str, str]]
    probe: object | None = None

    def features(self, raw, sentence_scores=None):
        return probe_features(self.heads, self.probe, raw, sentence_scores)

    def verify(self, extractor):
        if self.probe is not None and not np.array_equal(
            getattr(self.probe, "classes_", []), [0, 1]
        ):
            raise ValueError("Expected a fitted human/machine encoder probe in class order 0, 1")
        if set(self.identity) != set(MODEL_KEYS) or self.identity != extractor.identity:
            raise ValueError("Deep model was trained against different checkpoint files")

        if (
            getattr(self, "refit_provenance", None) is not None
            and self.fit_selection["quick_prefill"] != extractor.quick.lm.chunk_size
        ):
            raise ValueError("Refitted Deep model requires its training prefill size")

        provenance = getattr(self.probe, "training_provenance_", None)
        if provenance and (
            provenance.get("vector_version") != ENCODER_VECTOR_VERSION
            or provenance.get("encoder_sha256") != self.identity["ENCODER"].get("model.safetensors")
        ):
            raise ValueError("Frozen probe was fitted with a different encoder or vector schema")

    def save(self, path):
        save_artifact(self, path)

    @classmethod
    def load(cls, path):
        model = joblib.load(path)
        if (
            not isinstance(model, cls)
            or not isinstance(getattr(model, "identity", None), dict)
            or set(model.identity) != set(MODEL_KEYS)
            or not isinstance(model.stacker, DeepStacker)
            or model.stacker.feature_names
            != (DEEP_FEATURE_NAMES if model.probe is None else ProbeDeepStacker.FEATURES)
        ):
            raise ValueError("Incompatible Deep model")
        return model


class DeepEngine:
    def __init__(self, extractor, model):
        model.verify(extractor)
        self.extractor, self.model, self.backend = extractor, model, extractor.backend

    @classmethod
    def from_env(cls, quick_extractor=None):
        model = DeepModel.load(os.environ["VIBECHECKER_DEEP_MODEL"])
        return cls(DeepExtractor.from_env(quick_extractor), model)

    def stream(self, doc: Prepared):
        validate(doc, "deep")
        heads = self.model.heads
        parts, waveforms, sentences = [], [], []
        total = len(doc.chunks)
        for index, (chunk, (stats, waves)) in enumerate(
            zip(doc.chunks, self.extractor.pair.chunks(doc), strict=True), 1
        ):
            parts.append(stats)
            waveforms.extend(waves)
            items = [heads.sentence_item(s, w) for s, w in zip(chunk, waves, strict=True)]
            sentences.extend(items)
            yield {"type": "sentences", "items": items}
            yield {"type": "progress", "stage": "deep", "done": index, "total": total}
        raw = self.extractor.aggregate(
            doc, parts, waveforms, include_encoder_evidence=self.model.probe is not None
        )
        scores = [s["score"] for s in sentences]
        result = self.model.stacker.predict(self.model.features(raw, scores), doc.word_count)
        flags = heads.flags(raw)
        if "esl" in flags:
            # A caution can only widen the interval. Never feed the predicted
            # writer cohort or its probability into the headline classifier.
            ci = result["interval"]
            ci["low"] = max(0, ci["low"] - 5)
            ci["high"] = min(100, ci["high"] + 5)
        local = np.array([waveform_signals(w) for w in waveforms if len(w)])
        samples = {
            **raw.quick.samples,
            "e3": _samples(local[:, 0]),
            "e4": _samples(local[:, 1]),
            "e5": _samples(scores),
        }
        for signal in result["signals"]:
            if samples.get(signal["id"]):
                signal["samples"] = samples[signal["id"]]
        yield {
            "type": "result",
            "result": {
                **result,
                "wordCount": doc.word_count,
                "flags": flags,
                "sentences": sentences,
            },
        }

    def analyze(self, text):
        for event in self.stream(prepare(text)):
            if event["type"] == "result":
                return event["result"]
