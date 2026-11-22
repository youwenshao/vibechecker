"""Local descriptions of detector-like behaviour, separate from the verdict."""

import re
from functools import cache
from importlib.resources import files
from pathlib import Path

import yaml


@cache
def parameters():
    packaged = files("vibechecker_engine").joinpath("lenses/v1.yaml")
    path = (
        packaged if packaged.is_file() else Path(__file__).resolve().parents[2] / "lenses/v1.yaml"
    )
    return yaml.safe_load(path.read_text(encoding="utf8"))


def document_signals(values, text, words, config):
    perplexity, burst, _, _, encoder, _, _, length_sd, _ = values[:9]
    phrases = sum(
        len(re.findall(r"\b" + re.escape(p) + r"\b", text, re.IGNORECASE))
        for p in config["veriguide"]["phrases"]
    )
    scales = config["scales"]
    signals = {
        "encoder": encoder,
        "predictable": 1 / (1 + perplexity / scales["perplexity"]),
        "steady": 1 / (1 + burst),
        "uniform": 1 / (1 + length_sd / scales["sentence_length_sd"]),
        "overlap": min(1, scales["phrase_words"] * phrases / words),
    }
    return {
        name: sum(signals[key] * weight for key, weight in config[name]["weights"].items())
        for name in ("gptzero", "zerogpt", "grammarly", "veriguide")
    }


def lens_results(values, text, words, sentence_words_and_scores=()):
    config = parameters()
    result = {"version": config["version"], "turnitin": None}
    if sentence_words_and_scores:
        threshold = config["turnitin"]["high"]
        flagged = sum(size for size, score in sentence_words_and_scores if score >= threshold)
        share = round(100 * flagged / words)
        result["turnitin"] = "masked" if 0 < share < 20 else share
    for key, value in document_signals(values, text, words, config).items():
        low, high = config[key]["mixed"], config[key]["high"]
        result[key] = "high" if value >= high else "mixed" if value >= low else "low"
    return result
