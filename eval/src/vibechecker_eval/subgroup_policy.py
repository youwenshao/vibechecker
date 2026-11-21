"""Fit research-only band cutoffs and an optional score adjustment on calibration rows."""

from collections import defaultdict
from dataclasses import replace

import numpy as np
from scipy.special import expit, logit
from vibechecker_engine.stacker import _band_threshold

from .band_controls import high_cutoff as order_statistic_cutoff
from .metrics import length_bin, metrics, rate


def source(dataset):
    # Origin suffixes encode the answer. The admissions corpus is one source.
    if dataset in {"liang/college-human", "liang/college-ai"}:
        return "liang/college"
    return dataset


def keys(row):
    dataset = source(row.dataset)
    length = length_bin(row.words)
    return (f"source-length/{dataset}/{length}", f"length/{length}", f"source/{dataset}", "pooled")


def rescale(score, power):
    if score in (0, 1) or power == 1:
        return score
    return round(100 * expit(power * logit(score))) / 100


def fit(rows, high, *, adjust=False, guarded=False):
    if not rows or any(r.split != "calibration" for r in rows):
        raise ValueError("Only calibration records may fit a policy")
    cells = defaultdict(list)
    for row in rows:
        for key in keys(row):
            cells[key].append(row)
    powers = {}
    if adjust:
        for key, members in cells.items():
            if len(members) < 1000 or {r.label for r in members} != {0, 1}:
                continue

            def balanced_brier(power):
                return sum(
                    np.mean([(rescale(r.score, power) - y) ** 2 for r in members if r.label == y])
                    / 2
                    for y in (0, 1)
                )

            powers[key] = min((1, 0.5, 2), key=balanced_brier)
    policy = {"base_high": high, "powers": powers, "cutoffs": {}}
    for key, members in sorted(cells.items()):
        humans = [round(transform(r, policy) * 100) for r in members if r.label == 0]
        if guarded and len(humans) >= 149:
            cutoff, _ = order_statistic_cutoff(humans, previous_high=high)
        elif not guarded and len(humans) >= 50:
            cutoff = _band_threshold(np.asarray(humans), 0.02)
        else:
            continue
        if cutoff >= 1:
            policy["cutoffs"][key] = {
                "high": cutoff,
                "humans": len(humans),
                "documents": len(members),
            }
    return policy


def transform(row, policy):
    power = next((policy["powers"][k] for k in keys(row) if k in policy["powers"]), 1)
    return rescale(row.score, power)


def high_cutoff(row, policy):
    for key in keys(row):
        if key in policy["cutoffs"]:
            return policy["cutoffs"][key]["high"]
    return policy["base_high"]


def scorecard(rows, policy, mixed):
    groups = defaultdict(list)
    for row in rows:
        scored = replace(row, score=transform(row, policy))
        high = round(100 * scored.score) >= high_cutoff(row, policy)
        fields = [
            f"{k}/{getattr(row, k)}"
            for k in ("split", "dataset", "genre", "writer", "generator", "attack")
        ]
        fields.extend(keys(row))
        if row.genre == "essay" and row.writer == "ESL":
            fields.append("fairness/ESL-essay")
        for field in fields:
            groups[field].append((scored, high))
    summary = {}
    for name, entries in sorted(groups.items()):
        members, decisions = zip(*entries, strict=True)
        values = metrics(members, mixed, policy["base_high"] / 100)
        for label, field in [(0, "fpr_high"), (1, "recall_high")]:
            selected = [
                high for r, high in zip(members, decisions, strict=True) if r.label == label
            ]
            values[field] = rate(sum(selected), len(selected))
        del values["latency_ms"]
        summary[name] = values
    return summary
