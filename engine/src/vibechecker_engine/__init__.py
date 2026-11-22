import os

from .lenses import lens_results

from .signals import FEATURE_NAMES, FeatureExtractor, FeatureRow
from .stacker import QuickStacker, length_bin
from .text import Refusal

__all__ = [
    "FEATURE_NAMES",
    "FeatureExtractor",
    "FeatureRow",
    "QuickEngine",
    "QuickStacker",
    "Refusal",
    "length_bin",
]


class QuickEngine:
    def __init__(self, extractor: FeatureExtractor, stacker: QuickStacker):
        self.extractor = extractor
        self.stacker = stacker
        self.backend = extractor.backend

    @classmethod
    def from_env(cls):
        stacker = QuickStacker.load(os.environ["VIBECHECKER_STACKER"])
        return cls(FeatureExtractor.from_env(), stacker)

    def analyze(self, text: str):
        features = self.extractor.extract(text)
        result = self.stacker.predict(features.values, features.word_count)
        for signal in result["signals"]:
            samples = features.samples.get(signal["id"])
            if samples:
                signal["samples"] = samples
        return {
            **result,
            "wordCount": features.word_count,
            "flags": list(features.flags),
            "lenses": lens_results(features.values, text, features.word_count),
        }
