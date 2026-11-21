"""Frozen, source-grouped Deep cohorts and sentence labels for mixed documents."""

from dataclasses import dataclass

import numpy as np

from .loaders import fingerprint


def fold(item, purpose):
    # RAID has several generations and attacks for the same prompt.
    group = item.source_group or fingerprint(item.text)
    return int(fingerprint(purpose + group)[:8], 16) % 2


@dataclass(frozen=True)
class Splice:
    text: str
    labels: tuple[int, ...]


def mixed_documents(rows, seed):
    """Splice contiguous excerpts from two documents within the caller's partition."""
    from vibechecker_engine.text import prepare

    rng = np.random.default_rng(seed)
    groups = [[r for r in rows if r.label == label] for label in (0, 1)]
    for group in groups:
        rng.shuffle(group)
    for human, machine in zip(*groups):
        parts = []
        for item in (human, machine):
            sentences = prepare(item.text).sentences
            if len(sentences) < 2:
                break
            mid = len(sentences) // 2
            selected = sentences[:mid] if rng.integers(2) else sentences[mid:]
            parts.append([(item.text[s.start : s.end], item.label) for s in selected])
        if len(parts) != 2:
            continue
        if rng.integers(2):
            parts.reverse()
        left, right = parts
        left_text = " ".join(value for value, _ in left)
        text = left_text + "\n\n" + " ".join(value for value, _ in right)
        boundary = len(left_text)
        doc = prepare(text)
        if not 300 <= doc.word_count <= 2500:
            continue
        # Use exactly the runtime segmentation. A span crossing the splice lacks a unique label.
        if any(s.start < boundary < s.end for s in doc.sentences):
            continue
        labels = tuple(left[0][1] if s.end <= boundary else right[0][1] for s in doc.sentences)
        if set(labels) == {0, 1}:
            yield Splice(text, labels)


def reliability(rows):
    bins = []
    for index in range(10):
        members = [r for r in rows if min(9, int(r.score * 10)) == index]
        if members:
            bins.append(
                {
                    "lower": index / 10,
                    "upper": (index + 1) / 10,
                    "count": len(members),
                    "mean_score": float(np.mean([r.score for r in members])),
                    "observed_fraction": float(np.mean([r.label for r in members])),
                }
            )
    return bins


def sentence_metrics(truth, scores):
    from sklearn.metrics import f1_score, precision_score, recall_score

    if not truth:
        return {"count": 0, "f1": None, "precision": None, "recall": None}
    pred = np.asarray(scores) >= 0.5
    return {
        "count": len(truth),
        "f1": float(f1_score(truth, pred, zero_division=0)),
        "precision": float(precision_score(truth, pred, zero_division=0)),
        "recall": float(recall_score(truth, pred, zero_division=0)),
    }


def parity(current, reference, *, local_cpu_cuda=False):
    from .metrics import backend_parity

    for key in ("model_sha256", "weights", "scope"):
        if current[key] != reference[key]:
            raise ValueError(f"Deep parity requires identical {key}")
    # Earlier traces predate the configurable Quick prefill and used 64 tokens.
    prefill, reference_prefill = (trace.get("quick_prefill", 64) for trace in (current, reference))
    if any(type(value) is not int or value < 1 for value in (prefill, reference_prefill)):
        raise ValueError("Invalid Quick prefill in Deep trace")
    if prefill != reference_prefill:
        raise ValueError("Deep parity requires identical Quick prefill sizes")
    for trace in (current, reference):
        indices = np.asarray(list(trace["scores"].values()), dtype=float)
        if trace["sentences"].keys() != trace["scores"].keys() or not np.all(
            np.isfinite(indices) & (indices >= 0) & (indices <= 100) & (indices == np.rint(indices))
        ):
            raise ValueError("Invalid document or sentence trace")
    result = backend_parity(current, reference, local_cpu_cuda=local_cpu_cuda)
    max_delta = 0.0
    n = 0
    for key in current["scores"]:
        a, b = current["sentences"][key], reference["sentences"][key]
        if not a or [(x[0], x[1]) for x in a] != [(x[0], x[1]) for x in b]:
            raise ValueError("Deep parity requires identical sentence spans")
        scores = np.array([[x[2] for x in a], [x[2] for x in b]], dtype=float)
        if not np.all(np.isfinite(scores) & (scores >= 0) & (scores <= 1)):
            raise ValueError("Invalid sentence trace")
        deltas = np.abs(scores[0] - scores[1])
        max_delta = max(max_delta, float(max(deltas)))
        n += len(a)
    result.update(max_sentence_delta=max_delta, sentences=n, quick_prefill=prefill)
    result["pass"] = result["pass"] and max_delta <= 0.02 + 1e-12
    return result
