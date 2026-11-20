"""Sufficient statistics from one observer (base) and one performer (instruct) pass."""

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from .base import PairStats
from .mlx import select_device


def binoculars(stats: PairStats) -> float:
    denominator = stats.binoculars_cross.mean(dtype=np.float64)
    if not np.isfinite(denominator) or denominator >= 0:
        raise ValueError("Binoculars requires a nonzero cross entropy")
    return float(stats.logp_a.mean(dtype=np.float64) / denominator)


def fast_detect_gpt(stats: PairStats) -> float:
    # The variance of the sum is the sum of token variances, not the variance
    # of the concatenated distributions. Accumulate the reductions in fp64.
    mean = stats.cross.astype(np.float64)
    variance = np.maximum(stats.cross_sq - mean**2, 0).sum()
    return float((stats.logp_a - mean).sum() / np.sqrt(variance)) if variance > 0 else 0.0


def load_pair_model(path: Path, *, lazy: bool = False):
    from mlx_lm.utils import load_model

    config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    if config["model_type"] == "falcon":
        from .falcon import Falcon, FalconArgs

        return load_model(path, lazy=lazy, get_model_classes=lambda config: (Falcon, FalconArgs))
    return load_model(path, lazy=lazy)


class MLXPairBackend:
    def __init__(self, observer, performer, name, device, chunk_size=64):
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        self.observer, self.performer = observer, performer
        self.name, self.device, self.chunk_size = name, device, chunk_size

    @classmethod
    def from_paths(cls, observer_dir, performer_dir, requested=None):
        import mlx.core as mx

        name, device = select_device(requested)
        with mx.stream(device):
            if name == "mlx-metal":
                limit = 18 * 1024**3
                # Reject clearly oversized packs (especially bf16 Falcon) before
                # mapping a second model on the co-tenanted 32 GiB machine.
                pair_bytes = sum(
                    f.stat().st_size
                    for folder in (observer_dir, performer_dir)
                    for f in folder.glob("model*.safetensors")
                )
                if mx.get_active_memory() + pair_bytes >= limit:
                    raise ValueError("Selected pair exceeds the Metal memory budget")
                mx.set_memory_limit(limit)
                # Bound retained scratch buffers on the shared host. The inputs
                # and KV caches for a live pass remain in the active allocation.
                mx.set_cache_limit(512 * 1024**2)
            # Preserve the checkpoint's bf16 or packed weights. Only the
            # vocabulary reductions need fp32 for usable second moments.
            observer, _ = load_pair_model(observer_dir)
            performer, _ = load_pair_model(performer_dir)
        return cls(observer, performer, name, device)

    def caches(self):
        from mlx_lm.models.cache import make_prompt_cache

        return make_prompt_cache(self.observer), make_prompt_cache(self.performer)

    def pair_stats(self, ids: Sequence[int], start, stop, caches, pad_id) -> PairStats:
        """Advance both caches over input positions [start, stop) exactly once."""
        import mlx.core as mx

        if not 0 <= start <= stop <= len(ids):
            raise ValueError("Invalid pair slice")
        if start == stop:
            return PairStats(*(np.empty(0, dtype=np.float32) for _ in PairStats._fields))
        blocks = []
        with mx.stream(self.device):
            for i in range(start, stop, self.chunk_size):
                j = min(i + self.chunk_size, stop)
                context = mx.array([ids[i:j]])
                observer = self.observer(context, cache=caches[0])[0].astype(mx.float32)
                performer = self.performer(context, cache=caches[1])[0].astype(mx.float32)
                if observer.shape != performer.shape:
                    raise ValueError("Pair logits must use identical vocabulary dimensions")
                log_a = performer - mx.logsumexp(performer, axis=-1, keepdims=True)
                log_b = observer - mx.logsumexp(observer, axis=-1, keepdims=True)
                prob_b = mx.exp(log_b)
                cross = mx.sum(prob_b * log_a, axis=-1)
                second = mx.sum(prob_b * mx.square(log_a), axis=-1)
                target_ids = list(ids[i + 1 : j + 1])
                n = len(target_ids)
                # A harmless terminal gather keeps the kernel shape nonempty,
                # including when the final block contains only the last context.
                if j == len(ids):
                    target_ids.append(0)
                targets = mx.array(target_ids, dtype=mx.int32)[:, None]
                observed_a = mx.take_along_axis(log_a, targets, axis=-1)[:, 0]
                observed_b = mx.take_along_axis(log_b, targets, axis=-1)[:, 0]
                mx.eval(observed_a, observed_b, cross, second)
                cross = np.array(cross)
                keep = (
                    np.ones(j - i, dtype=bool) if pad_id is None else np.asarray(ids[i:j]) != pad_id
                )
                blocks.append(
                    PairStats(
                        np.array(observed_a)[:n],
                        cross[:n],
                        np.array(second)[:n],
                        np.array(observed_b)[:n],
                        cross[keep],
                    )
                )
        return PairStats.concatenate(blocks)
