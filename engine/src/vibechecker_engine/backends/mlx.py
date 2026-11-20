"""Teacher-forced next-token statistics with one KV cache per document."""

import platform
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from .base import TokenStats


def select_device(requested=None):
    import mlx.core as mx

    gpu_available = mx.default_device() == mx.gpu
    gpu_name = "mlx-metal" if platform.system() == "Darwin" else "mlx-cuda"
    name = requested or (gpu_name if gpu_available else "mlx-cpu")
    if name != "mlx-cpu" and (name != gpu_name or not gpu_available):
        raise RuntimeError(f"Requested MLX backend {name} is unavailable")
    return name, mx.cpu if name == "mlx-cpu" else mx.gpu


def _token_reductions(logits, targets):
    import mlx.core as mx

    selected = mx.take_along_axis(logits, targets, axis=1)
    log_probs = logits - mx.logsumexp(logits, axis=1, keepdims=True)
    logp = mx.take_along_axis(log_probs, targets, axis=1)[:, 0]
    rank = 1 + mx.sum(logits > selected, axis=1)
    entropy = -mx.sum(mx.exp(log_probs) * log_probs, axis=1)
    return logp, rank, entropy


class MLXBackend:
    def __init__(self, model, name, device, chunk_size=64):
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        self.model = model
        self.name = name
        self.device = device
        self.chunk_size = chunk_size
        self.reduce = _token_reductions

    def set_prefill(self, tokens):
        import mlx.core as mx

        if tokens < 1:
            raise ValueError("Quick prefill must be positive")
        self.chunk_size = tokens
        # Compile only pure vocabulary reductions. KV cache mutation and host
        # reads remain outside the graph, so documents never share cache state.
        self.reduce = (
            _token_reductions if tokens == 64 else mx.compile(_token_reductions, shapeless=True)
        )

    @classmethod
    def from_path(cls, path: Path, requested=None):
        import mlx.core as mx
        from mlx_lm.utils import load_model

        name, device = select_device(requested)
        with mx.stream(device):
            if name == "mlx-metal":
                mx.set_memory_limit(18 * 1024**3)
            model, _ = load_model(path)
            # For the 0.5B Quick LM this costs about 1 GB over bf16. On the M6
            # it reduced mean CPU/Metal log-probability drift by a factor of 18.
            model.set_dtype(mx.float32)
            mx.eval(model.parameters())
        return cls(model, name, device)

    def token_stats(self, ids: Sequence[int]) -> TokenStats:
        import mlx.core as mx
        from mlx_lm.models.cache import make_prompt_cache

        if len(ids) < 2:
            raise ValueError("At least two token IDs are required")
        observed, ranks, entropies = [], [], []
        with mx.stream(self.device):
            cache = make_prompt_cache(self.model)
            for start in range(0, len(ids) - 1, self.chunk_size):
                stop = min(start + self.chunk_size, len(ids) - 1)
                context = mx.array([ids[start:stop]])
                targets = mx.array(ids[start + 1 : stop + 1])[:, None]
                logits = self.model(context, cache=cache)[0].astype(mx.float32)
                logp, rank, entropy = self.reduce(logits, targets)
                # Materialize reductions before the next chunk. Holding lazy logits for
                # an entire essay would use gigabytes for Qwen's 150k-word vocabulary.
                mx.eval(logp, rank, entropy)
                observed.append(np.array(logp))
                ranks.append(np.array(rank))
                entropies.append(np.array(entropy))
        return TokenStats(
            np.concatenate(observed), np.concatenate(ranks), np.concatenate(entropies)
        )
