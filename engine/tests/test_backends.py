"""Use one set of tiny, deterministic Llama weights in both frameworks."""

import numpy as np
import pytest
from vibechecker_engine.backends.mlx import MLXBackend, select_device

mx = pytest.importorskip("mlx.core")
torch = pytest.importorskip("torch")


@pytest.fixture(scope="module")
def weights(tmp_path_factory):
    from transformers import LlamaConfig, LlamaForCausalLM

    out = tmp_path_factory.mktemp("tiny-llama")
    torch.manual_seed(319)
    config = LlamaConfig(
        vocab_size=64,
        hidden_size=16,
        intermediate_size=32,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=128,
        tie_word_embeddings=False,
        attention_dropout=0.0,
    )
    model = LlamaForCausalLM(config).float().eval()
    model.save_pretrained(out)
    return model, out


@pytest.mark.parametrize("chunk_size", [1, 3, 64])
def test_chunked_mlx_against_pytorch(weights, chunk_size):
    model, path = weights
    backend = MLXBackend.from_path(path, "mlx-cpu")
    backend.chunk_size = chunk_size
    ids = [5, 4, 3, 2, 5, 7, 9, 16]
    with torch.inference_mode():
        logits = model(torch.tensor([ids[:-1]])).logits[0]
        log_probs = logits.log_softmax(dim=-1)
        targets = torch.tensor(ids[1:]).unsqueeze(1)
        expected = log_probs.gather(1, targets)
        ranks = 1 + (log_probs > expected).sum(dim=1)
        entropy = -(log_probs.exp() * log_probs).sum(dim=1)
    actual = backend.token_stats(ids)
    np.testing.assert_allclose(actual.logp, expected.flatten().numpy(), atol=2e-5)
    np.testing.assert_array_equal(actual.rank, ranks.numpy())
    np.testing.assert_allclose(actual.entropy, entropy.numpy(), atol=2e-5)


@pytest.mark.skipif(not mx.metal.is_available(), reason="requires Apple Metal")
def test_cpu_and_metal(weights):
    _, path = weights
    ids = [2, 12, 41, 38, 19, 20, 8, 2, 14, 32, 7]
    cpu = MLXBackend.from_path(path, "mlx-cpu").token_stats(ids)
    metal = MLXBackend.from_path(path, "mlx-metal").token_stats(ids)
    # Metal's fused attention and CPU BLAS can differ in the fourth decimal place.
    # A rank change would be directionally meaningful even at this precision.
    np.testing.assert_allclose(metal.logp, cpu.logp, atol=1e-3)
    np.testing.assert_array_equal(metal.rank, cpu.rank)
    np.testing.assert_allclose(metal.entropy, cpu.entropy, atol=1e-3)


def test_reject_unavailable_backend():
    with pytest.raises(RuntimeError, match="unavailable"):
        select_device("mlx-unavailable")
