"""Document-level metrics. Undefined rates stay null instead of appearing as perfect zeros."""

from collections import defaultdict
from dataclasses import dataclass
from math import sqrt

import numpy as np
from sklearn.metrics import roc_auc_score, roc_curve


@dataclass(frozen=True)
class Observation:
    id: str
    label: int
    score: float
    dataset: str
    split: str
    genre: str
    writer: str
    generator: str
    attack: str
    words: int
    latency_ms: float | None


def length_bin(n):
    if n < 150:
        return "<150"
    if n < 300:
        return "150-299"
    if n < 600:
        return "300-599"
    return "600-1199" if n < 1200 else "1200+"


def rate(k, n):
    if not n:
        return {"count": 0, "denominator": 0, "rate": None, "wilson95": None}
    p = k / n
    z = 1.95996398454
    d = 1 + z**2 / n
    mid = (p + z**2 / (2 * n)) / d
    half = z * sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return {
        "count": k,
        "denominator": n,
        "rate": p,
        "wilson95": [max(0, mid - half), min(1, mid + half)],
    }


def metrics(rows, mixed, high):
    y = np.asarray([r.label for r in rows])
    p = np.asarray([r.score for r in rows])
    if not len(p) or not np.all(np.isfinite(p) & (p >= 0) & (p <= 1)):
        raise ValueError("Metrics need finite probabilities")
    ece = 0.0
    bins = np.minimum((p * 10).astype(int), 9)
    for idx in np.unique(bins):
        mask = bins == idx
        ece += float(mask.mean() * abs(y[mask].mean() - p[mask].mean()))
    auc = tpr = None
    if len(np.unique(y)) == 2:
        auc = float(roc_auc_score(y, p))
        f, t, _ = roc_curve(y, p)
        # A tied score must receive one decision at an attainable operating point.
        tpr = float(max(t[f <= 0.01]))
    human = p[y == 0]
    latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
    return {
        "count": len(rows),
        "ai_count": int(y.sum()),
        "auroc": auc,
        "tpr_at_1pct_fpr": tpr,
        "ece": ece,
        "brier": float(np.mean((y - p) ** 2)),
        "fpr_mixed_or_above": rate(int((human >= mixed).sum()), len(human)),
        "fpr_high": rate(int((human >= high).sum()), len(human)),
        "latency_ms": dict(zip(("p50", "p95"), np.percentile(latencies, [50, 95]).tolist()))
        if latencies
        else None,
    }


def summarize(rows, mixed, high):
    groups = defaultdict(list)
    for r in rows:
        for field in ("split", "dataset", "genre", "writer", "generator", "attack"):
            groups[f"{field}/{getattr(r, field)}"].append(r)
        groups[f"length/{length_bin(r.words)}"].append(r)
        if r.genre == "essay" and r.writer == "ESL":
            groups["fairness/ESL-essay"].append(r)
    return {
        "pooled": metrics(rows, mixed, high),
        **{k: metrics(v, mixed, high) for k, v in sorted(groups.items())},
    }


def gates(groups, *, quick, previous=None):
    gates = {}

    def test(name, value, target, at_least=False):
        passed = None if value is None else (value >= target if at_least else value <= target)
        gates[name] = {
            "value": value,
            "target": target,
            "status": "unmeasured" if passed is None else "pass" if passed else "fail",
        }

    essay = groups.get("genre/essay", {})
    test("essay_auroc", essay.get("auroc"), 0.85, at_least=True)
    test("pooled_ece", groups["pooled"]["ece"], 0.05)
    test(
        "worst_stratum_ece",
        max((g["ece"] for k, g in groups.items() if k != "pooled"), default=None),
        0.08,
    )
    test("human_essay_high_fpr", essay.get("fpr_high", {}).get("rate"), 0.02)
    esl = groups.get("fairness/ESL-essay", {}).get("fpr_high", {}).get("rate")
    toefl = groups.get("dataset/liang/toefl", {}).get("fpr_high", {}).get("rate")
    native = groups.get("writer/native_proxy", {}).get("fpr_high", {}).get("rate")
    test("esl_high_fpr", esl, 0.05)
    test("toefl_high_fpr", toefl, 0.05)
    test(
        "esl_native_gap",
        abs(esl - native) if esl is not None and native is not None else None,
        0.03,
    )
    test(
        "toefl_native_gap",
        abs(toefl - native) if toefl is not None and native is not None else None,
        0.03,
    )
    if previous:
        deltas = []
        for name, old in previous.items():
            current = groups.get(name, {})
            for metric, direction in (
                ("auroc", 1),
                ("tpr_at_1pct_fpr", 1),
                ("ece", -1),
                ("brier", -1),
                ("fpr_high", -1),
                ("fpr_mixed_or_above", -1),
            ):
                a, b = old.get(metric), current.get(metric)
                if metric.startswith("fpr"):
                    a, b = (a or {}).get("rate"), (b or {}).get("rate")
                if a is not None:
                    deltas.append(None if b is None else (a - b) * direction)
        worst = max(deltas) if deltas and None not in deltas else None
        test("max_metric_regression", worst, 0.01)
    return {
        "eligible": quick and all(g["status"] == "pass" for g in gates.values()),
        "checks": gates,
    }


def backend_parity(current, reference):
    if {current["backend"], reference["backend"]} != {"mlx-metal", "mlx-cuda"}:
        raise ValueError("Parity requires Metal and CUDA traces")
    if current["version"] != reference["version"] or current["manifest"] != reference["manifest"]:
        raise ValueError("Parity requires identical engine and dataset versions")
    left, right = current["scores"], reference["scores"]
    if left.keys() != right.keys() or not left:
        raise ValueError("Parity requires the same scored essays")
    deltas = [abs(v - right[k]) for k, v in left.items()]
    return {
        "documents": len(deltas),
        "max_index_delta": max(deltas),
        "mean_index_delta": float(np.mean(deltas)),
        "pass": len(deltas) >= 200 and max(deltas) <= 1,
    }
