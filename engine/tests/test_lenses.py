import pytest
from vibechecker_engine.deep import DeepEngine
from vibechecker_engine.lenses import lens_results, parameters


def test_turnitin_only_discloses_supported_shares():
    features = (20, 1, 2, 3, 0.4, 0.5, 5, 10, 0.2)
    threshold = parameters()["turnitin"]["high"]

    def read(flagged):
        return lens_results(features, "", 300, [(flagged, threshold), (300 - flagged, 0)])[
            "turnitin"
        ]

    assert lens_results(features, "", 300)["turnitin"] is None
    assert read(0) == 0
    assert read(3) == read(57) == "masked"
    assert read(60) == 20
    assert read(300) == 100


def test_lens_weights_are_monotone_and_qualitative_bands_ordered():
    config = parameters()
    for key in ("gptzero", "zerogpt", "grammarly", "veriguide"):
        assert config[key]["mixed"] < config[key]["high"]
        assert all(weight > 0 for weight in config[key]["weights"].values())
        assert sum(config[key]["weights"].values()) == 1


def test_advertised_v4_rejects_other_artifacts_before_loading_weights(tmp_path, monkeypatch):
    path = tmp_path / "model.joblib"
    path.write_bytes(b"other checkpoint")
    monkeypatch.setenv("VIBECHECKER_DEEP_MODEL", str(path))
    monkeypatch.setenv("ENGINE_VERSION", parameters()["model"])
    with pytest.raises(ValueError, match="frozen Phase 1.1 artifact"):
        DeepEngine.from_env()
