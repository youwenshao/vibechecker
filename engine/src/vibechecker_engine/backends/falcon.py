"""MLX inference for the original rotary, multi-query Falcon-7B checkpoints."""

from dataclasses import dataclass

import mlx.core as mx
from mlx import nn
from mlx_lm.models.base import BaseModelArgs, create_attention_mask, scaled_dot_product_attention


@dataclass
class FalconArgs(BaseModelArgs):
    model_type: str
    vocab_size: int
    hidden_size: int
    num_hidden_layers: int
    num_attention_heads: int
    layer_norm_epsilon: float = 1e-5
    multi_query: bool = True
    parallel_attn: bool = True
    alibi: bool = False
    new_decoder_architecture: bool = False
    bias: bool = False
    rope_theta: float = 10000.0
    activation: str = "gelu"
    ffn_hidden_size: int | None = None

    def __post_init__(self):
        if (
            not self.multi_query
            or not self.parallel_attn
            or self.alibi
            or self.new_decoder_architecture
            or self.activation != "gelu"
        ):
            raise ValueError("Expected the original Falcon-7B architecture")


class Attention(nn.Module):
    def __init__(self, args):
        super().__init__()
        self.heads = args.num_attention_heads
        self.dim = args.hidden_size // self.heads
        self.query_key_value = nn.Linear(
            args.hidden_size, args.hidden_size + 2 * self.dim, bias=args.bias
        )
        self.dense = nn.Linear(args.hidden_size, args.hidden_size, bias=args.bias)
        self.rope = nn.RoPE(self.dim, traditional=False, base=args.rope_theta)

    def __call__(self, x, mask, cache):
        b, n, width = x.shape
        q, k, v = mx.split(self.query_key_value(x), [width, width + self.dim], axis=-1)
        q = q.reshape(b, n, self.heads, self.dim).transpose(0, 2, 1, 3)
        k, v = k[:, None], v[:, None]
        offset = cache.offset if cache is not None else 0
        q, k = self.rope(q, offset=offset), self.rope(k, offset=offset)
        if cache is not None:
            k, v = cache.update_and_fetch(k, v)
        output = scaled_dot_product_attention(q, k, v, cache=cache, scale=self.dim**-0.5, mask=mask)
        return self.dense(output.transpose(0, 2, 1, 3).reshape(b, n, width))


class MLP(nn.Module):
    def __init__(self, args):
        super().__init__()
        dim = args.hidden_size
        inner = args.ffn_hidden_size or 4 * dim
        self.dense_h_to_4h = nn.Linear(dim, inner, bias=args.bias)
        self.dense_4h_to_h = nn.Linear(inner, dim, bias=args.bias)

    def __call__(self, x):
        return self.dense_4h_to_h(nn.gelu(self.dense_h_to_4h(x)))


class Block(nn.Module):
    def __init__(self, args):
        super().__init__()
        self.input_layernorm = nn.LayerNorm(args.hidden_size, eps=args.layer_norm_epsilon)
        self.self_attention = Attention(args)
        self.mlp = MLP(args)

    def __call__(self, x, mask, cache):
        normalized = self.input_layernorm(x)
        return x + (self.self_attention(normalized, mask, cache) + self.mlp(normalized))


class Transformer(nn.Module):
    def __init__(self, args):
        super().__init__()
        self.word_embeddings = nn.Embedding(args.vocab_size, args.hidden_size)
        self.h = [Block(args) for _ in range(args.num_hidden_layers)]
        self.ln_f = nn.LayerNorm(args.hidden_size, eps=args.layer_norm_epsilon)

    def __call__(self, ids, cache):
        x = self.word_embeddings(ids)
        mask = create_attention_mask(x, cache[0])
        for layer, state in zip(self.h, cache, strict=True):
            x = layer(x, mask, state)
        return self.ln_f(x)


class Falcon(nn.Module):
    def __init__(self, args):
        super().__init__()
        self.model_type = args.model_type
        self.transformer = Transformer(args)
        self.lm_head = nn.Linear(args.hidden_size, args.vocab_size, bias=False)

    @property
    def layers(self):
        return self.transformer.h

    def sanitize(self, weights):
        # Transformers may serialize only one copy of tied weights.
        if "lm_head.weight" not in weights:
            weights["lm_head.weight"] = weights["transformer.word_embeddings.weight"]
        return weights

    def __call__(self, ids, cache=None):
        return self.lm_head(self.transformer(ids, cache or [None] * len(self.layers)))
