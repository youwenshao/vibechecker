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


@pytest.mark.parametrize("chunk_size", [1, 3, 64])
def test_falcon_pair_cross_framework(tmp_path, chunk_size):
    from transformers import FalconConfig, FalconForCausalLM
    from vibechecker_engine.backends.pair import MLXPairBackend, binoculars, fast_detect_gpt

    config = FalconConfig(
        vocab_size=32,
        hidden_size=32,
        num_hidden_layers=2,
        num_attention_heads=4,
        multi_query=True,
        new_decoder_architecture=False,
        hidden_dropout=0,
        attention_dropout=0,
        parallel_attn=True,
        alibi=False,
    )
    torch.manual_seed(728)
    observer, performer = [FalconForCausalLM(config).float().eval() for _ in range(2)]
    paths = [tmp_path / "base", tmp_path / "instruct"]
    for model, path in zip((observer, performer), paths, strict=True):
        model.save_pretrained(path)
    ids = [2, 7, 3, 0, 4, 8, 9]
    tensor = torch.tensor([ids])
    with torch.inference_mode():
        obs = observer(tensor).logits[0]
        logits = performer(tensor).logits[0]
        labels = tensor[0, 1:]
        p = obs.softmax(dim=-1)
        log_a = logits.log_softmax(dim=-1)
        selected = log_a[:-1].gather(1, labels[:, None])[:, 0]
        cross = (p * log_a).sum(-1)
        variance = (p[:-1] * log_a[:-1].square()).sum(-1) - cross[:-1].square()
        expected_e3 = (selected - cross[:-1]).sum() / variance.sum().sqrt()
        expected_e4 = selected.mean() / cross[tensor[0] != 0].mean()
    backend = MLXPairBackend.from_paths(*paths, requested="mlx-cpu")
    backend.chunk_size = chunk_size
    caches = backend.caches()
    a = backend.pair_stats(ids, 0, 2, caches, 0)
    b = backend.pair_stats(ids, 2, len(ids), caches, 0)
    stats = a.concatenate([a, b])
    np.testing.assert_allclose(stats.logp_a, selected.numpy(), atol=1e-5)
    np.testing.assert_allclose(stats.cross, cross[:-1].numpy(), atol=1e-5)
    assert fast_detect_gpt(stats) == pytest.approx(expected_e3.item(), abs=3e-4)
    assert binoculars(stats) == pytest.approx(expected_e4.item(), abs=1e-5)


@pytest.mark.parametrize("bits", [4, 6, 8])
def test_falcon_packed_weights_reload(tmp_path, bits):
    import json

    from mlx_lm.utils import quantize_model, save_model
    from transformers import FalconConfig, FalconForCausalLM
    from vibechecker_engine.backends.pair import load_pair_model

    config = FalconConfig(
        vocab_size=64,
        hidden_size=64,
        num_hidden_layers=1,
        num_attention_heads=4,
        multi_query=True,
        new_decoder_architecture=False,
        parallel_attn=True,
        alibi=False,
    )
    source = tmp_path / "source"
    packed = tmp_path / "packed"
    torch.manual_seed(7)
    FalconForCausalLM(config).eval().save_pretrained(source)
    with mx.stream(mx.cpu):
        original, config = load_pair_model(source)
        ids = mx.array([[2, 3, 5]])
        expected = np.asarray(original(ids))
        quantized, config = quantize_model(original, config, group_size=64, bits=bits)
        save_model(packed, quantized)
        (packed / "config.json").write_text(json.dumps(config))
        restored, config = load_pair_model(packed)
        assert config["quantization"]["bits"] == bits
        np.testing.assert_allclose(np.asarray(restored(ids)), expected, atol=0.15)


def test_quick_compiled_prefill_matches_reference_across_tail_lengths(weights):
    _, path = weights
    backend = MLXBackend.from_path(path, "mlx-cpu")
    ids = [2, 4, 6, 9, 3, 5, 4, 14, 22]
    baseline = backend.token_stats(ids)
    backend.set_prefill(3)
    for length in (4, 6, 8, 9):
        actual = backend.token_stats(ids[:length])
        np.testing.assert_allclose(actual.logp, baseline.logp[: length - 1], atol=2e-5)
        np.testing.assert_allclose(actual.entropy, baseline.entropy[: length - 1], atol=2e-5)
        np.testing.assert_array_equal(actual.rank, baseline.rank[: length - 1])


def test_equal_length_encoder_batches_preserve_outputs():
    from transformers import ModernBertConfig, ModernBertForSequenceClassification
    from vibechecker_engine.signals import Encoder

    torch.manual_seed(85)
    config = ModernBertConfig(
        vocab_size=64,
        hidden_size=16,
        num_hidden_layers=2,
        num_attention_heads=4,
        intermediate_size=32,
        pad_token_id=0,
        cls_token_id=1,
        sep_token_id=2,
        local_attention=8,
    )
    config._attn_implementation = "eager"
    model = ModernBertForSequenceClassification(config).eval()
    ids = [[1, i, 4, 9, 5, 2] for i in (3, 6, 7, 8)] + [[1, 11, 2]]
    masks = [[1] + [0] * (len(row) - 2) + [1] for row in ids]

    def tokenizer(text, **kwargs):
        return {"input_ids": ids, "special_tokens_mask": masks}

    encoder = Encoder(model, tokenizer, torch.device("cpu"))
    expected, expected_windows = encoder.score("fixture")
    encoder.batch_windows = 2
    actual, actual_windows = encoder.score("fixture")
    assert actual == pytest.approx(expected, abs=1e-7)
    np.testing.assert_allclose(actual_windows, expected_windows, atol=1e-7)
