import json
from dataclasses import replace
from hashlib import sha256

import pytest
from vibechecker_eval.loaders import Example, partition, raid_examples, read_artifact
from vibechecker_eval.metrics import Observation, backend_parity, gates, metrics, rate, summarize
from vibechecker_eval.registry import Artifact, fetch, registry, select, verified_output
from vibechecker_eval.runner import sample


def row(label, score, **changes):
    base = Observation(
        "id",
        label,
        score,
        "source",
        "test",
        "essay",
        "unknown",
        "human" if label == 0 else "gpt",
        "none",
        200,
        10.0,
    )
    return replace(base, **changes)


def test_immutable_sources_and_monetization_filter(tmp_path):
    catalog = registry()
    assert select(catalog, ["liang", "asap"], True) == [catalog["asap"]]
    with pytest.raises(ValueError, match="excluded"):
        select(catalog, ["daigt"])
    with pytest.raises(ValueError, match="No eligible"):
        select(catalog, ["liang"], True)
    a = Artifact("fixture", "https://example.com", sha256(b"source").hexdigest(), "test")
    with verified_output(a, tmp_path) as temp:
        temp.write_bytes(b"source")
    assert fetch(a, tmp_path).read_bytes() == b"source"
    with pytest.raises(ValueError, match="Checksum mismatch"), verified_output(a, tmp_path) as temp:
        temp.write_bytes(b"changed")
    assert fetch(a, tmp_path).read_bytes() == b"source"
    (tmp_path / a.sha256).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Corrupt"):
        fetch(a, tmp_path)


def test_r2_roundtrip_rejects_corrupt_download(tmp_path, monkeypatch):
    import boto3
    from vibechecker_eval.registry import sync_r2

    digest = sha256(b"publisher bytes").hexdigest()
    artifact = Artifact("fixture", "https://example.com/input", digest, "test")
    datasets = [replace(registry()["liang"], artifacts=[artifact])]
    path = tmp_path / digest
    path.write_bytes(b"publisher bytes")
    objects = {}

    class Storage:
        def upload_file(self, filename, bucket, key):
            from pathlib import Path

            objects[bucket, key] = Path(filename).read_bytes()

        def download_file(self, bucket, key, filename):
            from pathlib import Path

            Path(filename).write_bytes(objects[bucket, key])

    monkeypatch.setenv("R2_ENDPOINT_URL", "https://account.r2.cloudflarestorage.com")
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: Storage())
    sync_r2(datasets, tmp_path, "push", "fixture")
    path.unlink()
    sync_r2(datasets, tmp_path, "pull", "fixture")
    assert path.read_bytes() == b"publisher bytes"
    objects["fixture", "datasets/sha256/" + digest] = b"bad transfer"
    with pytest.raises(ValueError, match="Checksum mismatch"):
        sync_r2(datasets, tmp_path, "pull", "fixture")
    assert path.read_bytes() == b"publisher bytes"


def test_publishers_labels_and_grouped_splits(tmp_path):
    d = registry()["mage"]
    p = tmp_path / "data"
    p.write_text("text,label,src\nhello,1,cmv_human\nthere,0,cmv_machine_gpt\n")
    rows = list(read_artifact(d, d.artifacts[0], p))
    assert [(r.label, r.split) for r in rows] == [(0, "test"), (1, "test")]
    records = list(
        raid_examples(
            [
                {"generation": "a", "model": "human", "attack": "none", "source_id": "prompt-1"},
                {"generation": "b", "model": "gpt", "attack": "swap", "source_id": "prompt-1"},
            ]
        )
    )
    assert records[0].split == records[1].split == partition("raid:prompt-1")
    assert records[0].label == 0 and records[1].label == 1


def test_dedup_and_bounded_sample():
    stream = [Example(str(i), i % 2, "x", "train", "other") for i in range(100)]
    got, skip = sample(stream + [replace(stream[5], split="test")], 6, 42, lambda _: 150)
    assert len(got) == 12 and skip["x/duplicate"] == 1
    assert got == sample(stream, 6, 42, lambda _: 150)[0]
    assert not any(item.split == "test" for item, _ in got)


def test_metrics_at_tied_threshold_and_wilson():
    rs = [row(0, 0.5), row(1, 0.5), row(1, 1), row(0, 0)]
    m = metrics(rs, 0.5, 0.9)
    assert m["auroc"] == 0.875
    assert m["tpr_at_1pct_fpr"] == 0.5
    assert m["ece"] == 0
    assert m["brier"] == 0.125
    assert m["fpr_mixed_or_above"]["rate"] == 0.5
    assert m["fpr_high"]["denominator"] == 2
    assert m["fpr_high"]["wilson95"][1] > 0
    assert rate(0, 0)["rate"] is None
    assert metrics([row(1, 1)], 0.5, 0.9)["auroc"] is None


def test_missing_fairness_blocks_gate_and_regressions_fail():
    rs = [row(0, 0.1), row(1, 0.9)]
    groups = summarize(rs, 0.5, 0.9)
    got = gates(groups, quick=True, previous={"pooled": {"brier": 0, "ece": 0}})
    assert not got["eligible"]
    assert got["checks"]["esl_high_fpr"]["status"] == "unmeasured"
    assert got["checks"]["max_metric_regression"]["status"] == "fail"


def test_paired_backend_comparison_requires_identical_documents():
    trace = {"version": "v1", "backend": "mlx-metal", "manifest": {}, "scores": {"a": 4}}
    ref = {**trace, "backend": "mlx-cuda", "scores": {"a": 5}}
    parity = backend_parity(trace, ref)
    assert parity["max_index_delta"] == 1 and not parity["pass"]
    with pytest.raises(ValueError, match="same scored essays"):
        backend_parity(trace, {**ref, "scores": {"b": 4}})


def test_end_to_end_baseline_and_enforce(tmp_path):
    from vibechecker_eval.cli import main

    # Keep the network and any student text outside the test suite.
    cache = tmp_path / "cache"
    cache.mkdir()
    data = registry()["liang"]
    artifacts = []
    for i, a in enumerate(data.artifacts):
        payload = json.dumps(
            [{"document": (f"term{i} " * 180), "score": 0.8 if i == 2 else 0.2}]
        ).encode()
        digest = sha256(payload).hexdigest()
        (cache / digest).write_bytes(payload)
        artifacts.append({**a.__dict__, "sha256": digest})
    import yaml

    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"datasets": [{**data.__dict__, "artifacts": artifacts}]}))
    args = ["baseline", "--registry", str(path), "--cache", str(cache), "--reports", str(tmp_path)]
    assert main(args) == 0 and main([*args, "--enforce"]) == 1
    report = (tmp_path / "hfopenai-liang-v1/report.json").read_text()
    assert '"count": 4' in report and "term0" not in report
