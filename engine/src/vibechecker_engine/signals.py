import os
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from itertools import batched, groupby
from pathlib import Path

import numpy as np

from .backends.mlx import MLXBackend
from .text import WORD, Prepared, prepare, validate

FEATURE_NAMES = (
    "perplexity",
    "sentence_nll_std",
    "log_rank",
    "entropy",
    "encoder_probability",
    "type_token_ratio",
    "mean_word_length",
    "sentence_length_std",
    "word_repetition",
)
DISPLAY_FEATURES = {"e1": 0, "e2": 2, "e6": 4, "stylometry": 5}


@dataclass(frozen=True)
class FeatureRow:
    values: tuple[float, ...]
    word_count: int
    flags: tuple[str, ...]
    samples: dict[str, list[float]]


def stylometry(doc: Prepared) -> tuple[float, ...]:
    words = [word.casefold() for word in doc.words]
    if not words:
        raise ValueError("At least one word is required")
    frequencies = Counter(words)
    return (
        len(frequencies) / len(words),
        float(np.mean([len(w) for w in words])),
        float(np.std([s.word_count for s in doc.sentences])),
        max(frequencies.values()) / len(words),
    )


def _samples(values):
    """Average consecutive observations to keep the stream bounded."""
    if len(values) < 2:
        return []
    return [float(np.mean(part)) for part in np.array_split(values, min(len(values), 16))]


def token_features(stats, offsets, doc):
    sentence_ends = [s.norm_end for s in doc.sentences]
    # A byte-level tokenizer may include preceding whitespace in its token span.
    groups = np.array(
        [
            min(bisect_right(sentence_ends, max(0, end - 1)), len(sentence_ends) - 1)
            for _, end in offsets
        ]
    )
    nll = -stats.logp.astype(float)
    counts = np.bincount(groups)
    sentence_nll = np.bincount(groups, weights=nll)[counts > 0] / counts[counts > 0]
    log_rank = np.log(stats.rank)
    return (
        (
            float(np.exp(nll.mean())),
            float(sentence_nll.std()),
            float(log_rank.mean()),
            float(stats.entropy.mean()),
        ),
        {"e1": _samples(np.exp(sentence_nll)), "e2": _samples(log_rank)},
    )


class Encoder:
    def __init__(self, model, tokenizer, device):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.batch_windows = 1

    @classmethod
    def load(cls, path, backend):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        device = {"mlx-metal": "mps", "mlx-cuda": "cuda", "mlx-cpu": "cpu"}[backend]
        tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        model = (
            AutoModelForSequenceClassification.from_pretrained(
                path, local_files_only=True, attn_implementation="eager", use_safetensors=True
            )
            .float()
            .eval()
            .to(device)
        )
        if model.config.num_labels != 2:
            raise ValueError("Expected a binary ModernBERT detector")
        return cls(model, tokenizer, device)

    def score(self, text):
        import torch

        windows = self.tokenizer(
            text,
            max_length=512,
            truncation=True,
            return_overflowing_tokens=True,
            return_special_tokens_mask=True,
            verbose=False,
        )
        scores = []
        windows_ids = windows["input_ids"]
        sizes = [
            len(ids) - sum(mask)
            for ids, mask in zip(windows_ids, windows["special_tokens_mask"], strict=True)
        ]
        with torch.inference_mode():
            # Batch complete windows without padding. A shorter final window
            # retains precisely its original positions and attention mask.
            for _, equal_length in groupby(windows_ids, key=len):
                for batch in batched(equal_length, self.batch_windows):
                    tensor = torch.tensor(batch, device=self.device)
                    logits = self.model(
                        input_ids=tensor, attention_mask=torch.ones_like(tensor)
                    ).logits
                    scores.append(torch.softmax(logits.float(), dim=-1)[:, 1])
        scores = torch.cat(scores).cpu().tolist()
        return float(np.average(scores, weights=sizes)), _samples(scores)


class FeatureExtractor:
    def __init__(self, lm, tokenizer, encoder):
        self.lm = lm
        self.backend = lm.name
        self.tokenizer = tokenizer
        self.encoder = encoder

    @classmethod
    def from_env(cls):
        from transformers import AutoTokenizer

        lm_dir = Path(os.environ["VIBECHECKER_LM"])
        encoder_dir = Path(os.environ["VIBECHECKER_ENCODER"])
        if not lm_dir.is_dir() or not encoder_dir.is_dir():
            raise ValueError("Local LM and encoder directories are required")
        lm = MLXBackend.from_path(lm_dir, os.getenv("VIBECHECKER_BACKEND"))
        tokenizer = AutoTokenizer.from_pretrained(lm_dir, local_files_only=True, use_fast=True)
        extractor = cls(lm, tokenizer, Encoder.load(encoder_dir, lm.name))
        if prefill := os.getenv("VIBECHECKER_QUICK_PREFILL"):
            extractor.set_prefill(int(prefill))
        return extractor

    def set_prefill(self, tokens):
        self.lm.set_prefill(tokens)
        self.encoder.batch_windows = 1 if tokens == 64 else 2

    def extract(self, text: str) -> FeatureRow:
        doc = prepare(text)
        validate(doc)
        return self.extract_prepared(doc)

    def extract_prepared(self, doc: Prepared) -> FeatureRow:
        encoded = self.tokenizer(
            doc.normalized, return_offsets_mapping=True, add_special_tokens=False, verbose=False
        )
        ids, offsets = encoded["input_ids"], encoded["offset_mapping"]
        # Qwen has no BOS. Leave the unconditioned first token out on that model.
        if self.tokenizer.bos_token_id is not None:
            ids = [self.tokenizer.bos_token_id, *ids]
        else:
            offsets = offsets[1:]
        stats = self.lm.token_stats(ids)
        features, samples = token_features(stats, offsets, doc)
        encoder, samples["e6"] = self.encoder.score(doc.normalized)
        chunk_ratios = []
        for chunk in doc.chunks:
            words = [
                w.casefold() for s in chunk for w in WORD.findall(s.normalized, concurrent=False)
            ]
            if words:
                chunk_ratios.append(len(set(words)) / len(words))
        samples["stylometry"] = _samples(chunk_ratios)
        values = (*features, encoder, *stylometry(doc))
        if not np.all(np.isfinite(values)):
            raise ValueError("Detector produced a non-finite feature")
        return FeatureRow(values, doc.word_count, doc.flags, samples)
