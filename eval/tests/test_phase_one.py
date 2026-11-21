from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from vibechecker_eval.deep_cohort import (
    fold,
    mixed_documents,
    parity,
    reliability,
    sentence_metrics,
)
from vibechecker_eval.experiments import bakeoff
from vibechecker_eval.loaders import Example
from vibechecker_eval.metrics import Observation, gates, summarize


def document(label, name):
    words = "A writer described how the town library served the community during the winter"
    return " ".join(f"{words} in {name} number {i}." for i in range(24))


def test_mixed_origins_follow_the_runtime_sentence_boundaries():
    from vibechecker_engine.text import prepare

    rows = [
        Example(document(y, name), y, "fixture", "train", "essay", source_group="one")
        for y, name in enumerate(("Seoul", "Tokyo"))
    ]
    (mix,) = mixed_documents(rows, 7)
    assert 300 <= prepare(mix.text).word_count <= 2500
    assert set(mix.labels) == {0, 1}
    for s, label in zip(prepare(mix.text).sentences, mix.labels, strict=True):
        assert ("Tokyo" if label else "Seoul") in s.normalized
    assert list(mixed_documents(rows, 7)) == [mix]
    for purpose in ("head", "bakeoff"):
        assert fold(rows[0], purpose) == fold(rows[1], purpose)


def test_parity_checks_sentence_offsets_artifacts_and_minimum_count():
    def trace(backend, n):
        return {
            "version": "v1",
            "backend": backend,
            "scope": {},
            "manifest": {},
            "model_sha256": "f",
            "weights": {"pair": "a"},
            "scores": {str(i): 20 for i in range(n)},
            "sentences": {str(i): [[0, 7, 0.6]] for i in range(n)},
        }

    a, b = trace("mlx-metal", 200), trace("mlx-cuda", 200)
    assert parity(a, b)["pass"]
    assert parity({**a, "quick_prefill": 64}, b)["quick_prefill"] == 64
    with pytest.raises(ValueError, match="identical Quick prefill"):
        parity({**a, "quick_prefill": 256}, b)
    with pytest.raises(ValueError, match="Invalid Quick prefill"):
        parity({**a, "quick_prefill": None}, b)
    assert parity({**a, "quick_prefill": 256}, {**b, "quick_prefill": 256})["pass"]
    b["sentences"]["0"][0][2] = 0.62
    assert parity(a, b)["pass"]
    b["sentences"]["0"][0][2] = 0.63
    assert not parity(a, b)["pass"]
    b["sentences"]["0"][0][1] = 8
    with pytest.raises(ValueError, match="sentence spans"):
        parity(a, b)
    with pytest.raises(ValueError, match="weights"):
        parity(a, {**a, "weights": {"pair": "other"}})
    assert not parity(trace("mlx-metal", 199), trace("mlx-cuda", 199))["pass"]


def candidate(bits, tpr=0.9, esl=0.03, gb=14):
    return {
        "mode": "deep",
        "scope": {"cohort": "validation", "scored_ids_sha256": "abc"},
        "pair_bits": bits,
        "pair_family": "same",
        "backend": "mlx-metal" if bits else "mlx-cuda",
        "precision": f"{bits}bit" if bits else "bf16",
        "peak_bytes": gb * 1024**3,
        "metrics": {
            "genre/essay": {"tpr_at_1pct_fpr": tpr},
            "fairness/ESL-essay": {"fpr_high": {"rate": esl}},
        },
        "model_sha256": "model",
        "weights": {"pair": str(bits)},
    }


def test_bakeoff_requires_same_cohort_and_rejects_over_cap_and_unfair_candidates():
    reports = [
        candidate(None, 0.95),
        candidate(4, 0.85),
        candidate(6, 0.96, 0.07),
        candidate(8, 0.99, gb=19),
    ]
    result = bakeoff(reports)
    assert result["selected"]["bits"] == 4
    assert result["selected"]["tpr_delta_from_bf16"] == pytest.approx(-0.1)
    with pytest.raises(ValueError, match="Missing"):
        bakeoff(reports[:-1])
    with pytest.raises(ValueError, match="validation cohort"):
        bakeoff([{**reports[0], "scope": {"cohort": "test"}}, *reports[1:]])
    assert not bakeoff([reports[0], candidate(4, esl=None), *reports[2:]])["pass"]


def test_missing_fairness_is_unmeasured_and_reliability_bins_use_scores():
    row = Observation(
        "a", 0, 0.12, "liang/hewlett", "test", "essay", "native_proxy", "human", "none", 320, 1
    )
    rows = [row, replace(row, id="b", label=1, score=1.0)]
    result = gates(summarize(rows, 0.5, 0.9), quick=False, deep=True)
    assert result["checks"]["essay_auroc"]["target"] == 0.9
    assert result["checks"]["toefl_high_fpr"]["status"] == "unmeasured"
    assert not result["eligible"]
    bars = reliability(rows)
    assert bars[0]["mean_score"] == 0.12
    assert bars[-1] == {
        "lower": 0.9,
        "upper": 1,
        "count": 1,
        "mean_score": 1,
        "observed_fraction": 1,
    }
    assert sentence_metrics([0, 1], [0.4, 0.6])["f1"] == 1
    assert sentence_metrics([], [])["f1"] is None


def test_partial_bakeoff_keeps_projection_and_measured_scores_separate(tmp_path):
    import json

    from vibechecker_eval.cli import main
    from vibechecker_eval.deep_runner import write_json

    scored, rejected, out = (
        tmp_path / name for name in ("four.json", "eight-preflight.json", "summary.json")
    )
    write_json(candidate(4), scored)
    assert (
        main(
            [
                "memory-preflight",
                "--pair-family",
                "same",
                "--bits",
                "8",
                "--projected-bytes",
                str(20 * 1024**3),
                "--basis",
                "Fixture footprint projection",
                "--out",
                str(rejected),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "bakeoff",
                str(scored),
                "--partial",
                "--rank-provisional",
                "--rejected",
                str(rejected),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    result = json.loads(out.read_bytes())
    assert not result["pass"] and result["selected"] is None
    assert result["provisional_ranking"] == [{"family": "same", "bits": 4}]
    assert not result["candidates"][0]["eligible"]
    assert result["candidates"][0]["tpr_delta_from_bf16"] is None
    assert result["preflight_rejections"][0]["kind"] == "projected_footprint"
    missing = {r["precision"]: r["status"] for r in result["missing_measurements"]}
    assert missing == {
        "bf16": "unmeasured",
        "6bit": "unmeasured",
    }
    with pytest.raises(ValueError, match="Missing"):
        main(["bakeoff", str(scored), "--out", str(out)])
    with pytest.raises(ValueError, match="duplicate"):
        bakeoff([candidate(8)], partial=True, rejected=[json.loads(rejected.read_bytes())])

    # A documented over-cap quantization accounts for that slot in a complete comparison.
    bf16, six = tmp_path / "baseline.json", tmp_path / "six.json"
    write_json(candidate(None), bf16)
    write_json(candidate(6, tpr=0.95), six)
    assert (
        main(
            [
                "bakeoff",
                str(scored),
                str(six),
                str(bf16),
                "--rejected",
                str(rejected),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    complete = json.loads(out.read_bytes())
    assert complete["pass"] and complete["selected"]["bits"] == 6
    assert complete["missing_measurements"] == []
    assert [r["bits"] for r in complete["preflight_rejections"]] == [8]
    assert all(c["bits"] != 8 for c in complete["candidates"])

    preflight = json.loads(rejected.read_bytes())
    with pytest.raises(ValueError, match="Missing.*bf16"):
        bakeoff([candidate(4), candidate(6)], rejected=[preflight])
    with pytest.raises(ValueError, match="Invalid"):
        bakeoff([candidate(4), candidate(6)], rejected=[{**preflight, "bits": None}])
    with pytest.raises(ValueError, match="Invalid"):
        bakeoff([candidate(None), candidate(4), candidate(6)], rejected=[{**preflight, "bytes": 1}])
    failed = bakeoff(
        [candidate(None), candidate(4, esl=0.5), candidate(6, gb=20)], rejected=[preflight]
    )
    assert not failed["pass"] and failed["selected"] is None
    partial = bakeoff(
        [candidate(None), candidate(4), candidate(6)], rejected=[preflight], partial=True
    )
    assert not partial["pass"] and partial["selected"] is None


def test_verified_loader_keeps_unknown_writer_out_of_the_negative_training_class():
    from vibechecker_eval.loaders import human_essays

    rows = list(
        human_essays(
            [{"full_text": str(i), "ell_status": s} for i, s in enumerate(("No", "Yes", "NA"))],
            "asap",
        )
    )
    assert [r.ell_label for r in rows] == [0, 1, None]


def test_m6_evidence_is_bound_to_the_measured_artifact_and_latency(tmp_path):
    from vibechecker_eval.deep_runner import write_json
    from vibechecker_eval.experiments import hardware_evidence

    path = tmp_path / "load.json"
    args = SimpleNamespace(
        reference_report=None, bakeoff_report=None, load_report=path, version="v1"
    )
    trace = {"model_sha256": "chosen", "weights": {"pair": "v1"}}
    healthy = {"loaded": True, "last_exit": 0, "runs": 5}
    quick = [{"ms": 1999}] * 95 + [{"ms": 2500}] * 5
    deep = [{"ms": 24999, "chunks": 10, "first_chunk_ms": 2500}] * 19 + [
        {"ms": 26000, "chunks": 9, "first_chunk_ms": 2500}
    ]
    measured = {
        "version": "v1",
        "model_sha256": "chosen",
        "backend": "mlx-metal",
        "passed": True,
        "quick_concurrency": 5,
        "quick_words": 1000,
        "deep_words": 2000,
        "quick": quick,
        "deep": deep,
        "beat_ad_job": "system/hk.beatad.px-backup",
        "beat_ad_health": [healthy] * 21,
        "beat_ad_healthy": True,
        "peak_bytes": 12 * 1024**3,
        "quick_p95_ms": 1999,
        "deep_p95_ms": 24999,
    }
    write_json(measured, path)
    assert hardware_evidence(args, trace, 4)["m6_load"]["pass"]
    assert hardware_evidence(args, {**trace, "quick_prefill": 64}, 4)["m6_load"]["pass"]
    assert not hardware_evidence(args, {**trace, "quick_prefill": 256}, 4)["m6_load"]["pass"]
    write_json({**measured, "quick_prefill": 256}, path)
    assert hardware_evidence(args, {**trace, "quick_prefill": 256}, 4)["m6_load"]["pass"]
    for change in (
        {"model_sha256": "other"},
        {"quick_p95_ms": 1998},
        {"deep_p95_ms": 25000},
        {"quick_concurrency": 1},
        {"quick_words": 500},
        {"deep_words": 1000},
        {"quick": quick[:-1]},
        {"deep": deep[:-1]},
        {"quick": [*quick[1:], {"error": "busy"}]},
        {"deep": [*deep[1:], {"ms": 20000, "first_chunk_ms": None, "chunks": 0}]},
        {"beat_ad_healthy": False},
        {"beat_ad_health": [healthy] * 20},
        {"beat_ad_health": [healthy] * 10 + [{**healthy, "loaded": False}] + [healthy] * 10},
        {"beat_ad_health": [healthy] * 10 + [{**healthy, "last_exit": 1}] + [healthy] * 10},
        {"quick_prefill": 256},
        {"peak_bytes": 19 * 1024**3},
        {"quick": [{"ms": 2001}] * 100, "quick_p95_ms": 2001},
        {"deep": [{**deep[0], "ms": 25001}] * 20, "deep_p95_ms": 25001},
    ):
        write_json({**measured, **change}, path)
        assert not hardware_evidence(args, trace, 4)["m6_load"]["pass"]


def test_training_evaluates_disjoint_head_stacker_calibration_and_spliced_test(
    tmp_path, monkeypatch
):
    from vibechecker_engine.deep import DeepDocument, DeepEngine, DeepExtractor, DeepModel
    from vibechecker_engine.signals import FeatureRow
    from vibechecker_engine.text import prepare
    from vibechecker_eval import deep_runner, experiments
    from vibechecker_eval.registry import registry

    rows = []
    for split in ("train", "calibration", "test"):
        for y in (0, 1):
            for sub in (0, 1):
                for i in range(3):
                    name = f"{['Seoul', 'Tokyo'][y]}-{split}-{sub}-{i}"
                    r = Example(
                        document(y, name),
                        y,
                        "raid-attacks" if i != 2 else "asap",
                        split,
                        "essay",
                        writer="ESL" if i == 1 and not y else "unknown",
                        attack="attack" if i == 1 else "none",
                        ell_label=int(i == 1) if not y else None,
                    )
                    while fold(r, "head" if split == "train" else "bakeoff") != sub:
                        r = replace(r, source_group=(r.source_group or name) + "x")
                    rows.append(r)

    def extract(self, text):
        doc = prepare(text)
        waves = tuple(
            np.tile([1.0 + ("Tokyo" in s.normalized), -3.0, 1.0, -1.0], (10, 1))
            for s in doc.sentences
        )
        score = np.mean([w[0, 0] for w in waves]) - 1
        return DeepDocument(
            FeatureRow((float(score),) * 9, doc.word_count, (), {}),
            waves,
            1.0,
            0.5,
            (float(score),) * 11,
            (float(score),) * 18,
        )

    class Fixture:
        backend = "mlx-cpu"
        prefill = 64

        def __init__(self):
            self.quick = SimpleNamespace(lm=SimpleNamespace(chunk_size=self.prefill))
            self.identity = {
                name: {"model.safetensors": "a" * 64}
                for name in ("LM", "ENCODER", "PAIR_OBSERVER", "PAIR_PERFORMER")
            }

    Fixture.extract = extract
    monkeypatch.setattr(DeepExtractor, "from_env", Fixture)

    def analyze(self, text):
        raw = self.extractor.extract(text)
        result = self.model.stacker.predict(self.model.heads.features(raw), raw.quick.word_count)
        result.update(
            flags=self.model.heads.flags(raw),
            sentences=[
                self.model.heads.sentence_item(s, w)
                for s, w in zip(prepare(text).sentences, raw.waveforms, strict=True)
            ],
        )
        return result

    monkeypatch.setattr(DeepEngine, "analyze", analyze)
    monkeypatch.setattr(deep_runner, "examples", lambda datasets, cache: iter(rows))
    monkeypatch.setattr(experiments, "pair_info", lambda: ([], [{"model_type": "fixture"}] * 2, 4))
    monkeypatch.setattr(experiments, "peak_bytes", lambda _backend: 1000)
    args = SimpleNamespace(
        cache=Path("."),
        limit_per_class=8,
        seed=42,
        version="fixture",
        commercial_only=False,
        cohort="test",
        model_in=None,
        model_out=tmp_path / "m.joblib",
        trace_out=tmp_path / "trace.json",
        compare_trace=None,
        previous=None,
        load_report=None,
        bakeoff_report=None,
        reference_report=None,
        pair_family=None,
        reports=tmp_path,
    )
    result = deep_runner.run_deep(args, [registry()["asap"]])
    assert result["fit_counts"]["head_documents"] == 6
    assert result["fit_counts"]["mixed_training_documents"] > 0
    assert result["mixed_sentence_metrics"]["count"] > 0
    assert result["metrics"]["pooled"]["count"] == 6
    assert not result["release_ready"]
    for path in (args.trace_out, tmp_path / "fixture/report.json"):
        assert "town library" not in path.read_text()
    fitted = {
        "seed": 42,
        "limit_per_class_per_dataset_split": 8,
        "dataset_order": ["asap"],
        "quick_prefill": 64,
    }
    assert result["fit_selection"] == fitted

    model = DeepModel.load(args.model_out)
    assert model.fit_selection == fitted
    args.model_in, args.model_out = args.model_out, None
    args.limit_per_class, args.seed = 96, 7
    Fixture.prefill = 256
    scored = deep_runner.run_deep(args, [registry()["asap"]])
    assert scored["scope"]["limit_per_class_per_dataset_split"] == 96
    assert scored["scope"]["seed"] == 7
    assert scored["fit_selection"] == fitted
    assert scored["quick_prefill"] == 256
    assert deep_runner.read(args.trace_out)["quick_prefill"] == 256
    assert scored["model_sha256"] == result["model_sha256"]

    del model.fit_selection
    model.save(args.model_in)
    args.previous = tmp_path / "previous.json"
    args.previous.write_bytes((tmp_path / "fixture/report.json").read_bytes())
    earlier = deep_runner.run_deep(args, [registry()["asap"]])
    assert earlier["fit_selection"] is None and earlier["fit_counts"] == scored["fit_counts"]
    assert earlier["regression_reference"] == {
        "version": scored["version"],
        "model_sha256": scored["model_sha256"],
        "report_sha256": deep_runner.sha256(args.previous),
    }
