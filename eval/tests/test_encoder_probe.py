import sqlite3
from dataclasses import replace

import joblib
import numpy as np
import pytest
from vibechecker_eval.deep_cohort import fold
from vibechecker_eval.encoder_probe import _source_folds, collect, fit, open_cache, training_sample
from vibechecker_eval.loaders import Example, fingerprint
from vibechecker_eval.source_groups import human_source_aliases


def test_probe_excludes_protected_source_groups_and_cross_split_duplicate_text():
    samples = [
        Example(f"Document {i}", i % 2, "raid", "train", "other", source_group=f"group-{i}")
        for i in range(64)
    ]
    head = [r for r in samples if fold(r, "head") == 0]
    duplicate = replace(head[0], split="test", source_group="different-source")
    conflict = replace(head[1], label=1 - head[1].label)
    shared_group = replace(head[2], text="A different protected passage", split="calibration")
    rows = training_sample(
        [shared_group, *samples, duplicate, conflict],
        lambda _: 350,
        source_aliases=human_source_aliases([*samples, duplicate, conflict, shared_group]),
        seed=42,
        human_cap=64,
        clean_cap=64,
        attack_cap=64,
    )
    assert {key for key, _, _ in rows} == {fingerprint(r.text) for r in head[3:]}
    assert all(group == fingerprint(r.source_group) for _, group, r in rows)


def test_probe_sampling_is_order_invariant_and_capped_per_label_source():
    samples = [
        Example(
            f"Document {i}",
            i % 2,
            "raid",
            "train",
            "other",
            generator="human" if i % 2 == 0 else "example",
            source_group=f"group-{i}",
        )
        for i in range(150)
    ]
    args = {
        "source_aliases": human_source_aliases(samples),
        "seed": 42,
        "human_cap": 5,
        "clean_cap": 4,
        "attack_cap": 3,
    }
    chosen = training_sample(samples, lambda _: 300, **args)
    assert len(chosen) == 9
    assert chosen == training_sample(reversed(samples), lambda _: 300, **args)
    assert not training_sample(samples, lambda _: 299, **args)


def test_embedding_cache_rejects_a_different_extractor(tmp_path):
    path = tmp_path / "numeric.sqlite"
    open_cache(path, {"encoder": "a"}).close()
    open_cache(path, {"encoder": "a"}).close()
    with pytest.raises(ValueError, match="different extraction profile"):
        open_cache(path, {"encoder": "b"})


def test_encoder_training_cannot_overwrite_its_input_cache(tmp_path):
    from vibechecker_eval.encoder_probe import main

    path = tmp_path / "numeric.sqlite"
    path.write_bytes(b"existing cache")
    with pytest.raises(SystemExit):
        main(
            [
                "--features",
                str(path),
                "--model-out",
                str(path),
                "--report",
                str(tmp_path / "fit.json"),
            ]
        )
    assert path.read_bytes() == b"existing cache"


def test_cached_only_refuses_writes_and_missing_training_vectors(tmp_path):
    path = tmp_path / "numeric.sqlite"
    open_cache(path, {"encoder": "a"}).close()
    db = open_cache(path, {"encoder": "a"}, cached_only=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("INSERT INTO vectors VALUES ('id', NULL)")
        with pytest.raises(ValueError, match="missing a selected training row"):
            collect(
                [("id", "group", None)],
                db,
                lambda: pytest.fail("Encoder was loaded"),
                cached_only=True,
            )
    finally:
        db.close()


def test_encoder_uses_the_first_committed_vector_when_fits_overlap(tmp_path):
    from types import SimpleNamespace

    path = tmp_path / "numeric.sqlite"
    db = open_cache(path, {"encoder": "a"})
    doc = Example(
        "The public library is a quiet place to read a book. " * 32, 0, "asap", "train", "essay"
    )
    key = fingerprint(doc.text)
    first = np.ones(769, dtype="<f4")

    def concurrent_evidence(_text):
        with sqlite3.connect(path) as other:
            other.execute("INSERT INTO vectors VALUES (?, ?)", (key, first.tobytes()))
        return SimpleNamespace(vector=np.zeros(769, dtype="<f4"))

    try:
        rows = collect([(key, key, doc)], db, lambda: SimpleNamespace(evidence=concurrent_evidence))
    finally:
        db.close()
    np.testing.assert_array_equal(rows[0][-1], first)


def test_svm_sigmoid_uses_source_disjoint_margin_folds_and_survives_reload(tmp_path):
    rng = np.random.default_rng(2026)
    rows = []
    for i in range(90):
        for label in (0, 1):
            vector = rng.normal(size=12) + label
            rows.append((f"{i}-{label}", f"source-{i}", label, f"test-{label}", vector))
    groups = np.asarray([row[1] for row in rows])
    dev = _source_folds(groups, 42, "probe-validation", 5) == 0
    model, provenance = fit(rows, 42, candidate="svm-c16")
    assert provenance["inner_validation_n"] == int(dev.sum())
    assert provenance["inner_train_groups"] + provenance["inner_validation_groups"] == 90
    assert provenance["inner_validation_group_ids_sha256"] == fingerprint(
        " ".join(sorted(set(groups[dev])))
    )
    assert provenance["candidates"][0]["human_n"] == int(dev.sum()) // 2
    assert set(groups[~dev]).isdisjoint(groups[dev])
    assert set(np.concatenate([val for _, val in model.cv])) == set(range(len(rows)))
    for train, val in model.cv:
        assert set(groups[train]).isdisjoint(groups[val])
    assert model.classes_.tolist() == [0, 1]
    assert model.ensemble is False
    assert model.estimator.steps[-1][1].C == 16
    x = np.stack([row[4] for row in rows[:3]])
    probabilities = model.predict_proba(x)
    assert np.isfinite(probabilities).all()
    np.testing.assert_allclose(probabilities.sum(axis=1), 1)
    path = tmp_path / "svm-probe.joblib"
    joblib.dump(model, path)
    np.testing.assert_array_equal(joblib.load(path).predict_proba(x), probabilities)


def test_probe_quarantines_machine_derivatives_without_refilling_the_reservoir():
    candidates = [
        Example(f"Generated passage {i}", 1, "raid", "train", "other", source_group=f"g-{i}")
        for i in range(40)
    ]
    args = {"seed": 42, "human_cap": 1, "clean_cap": 3, "attack_cap": 1}
    # Human originals are too short to enter training. One sits in another
    # publisher group on the protected split and identifies the ambiguous group.
    expected = training_sample(
        candidates, lambda _: 400, source_aliases=human_source_aliases(candidates), **args
    )
    implicated = expected[0][2].source_group
    a = replace(expected[0][2], label=0, text="Original context", source_group=implicated)
    b = replace(a, text=" ORIGINAL  context ", split="test", source_group="other-publisher-id")
    stream = [*candidates, a, b]
    aliases = human_source_aliases(stream)
    selected = training_sample(
        stream, lambda t: 10 if "context" in t.lower() else 400, source_aliases=aliases, **args
    )
    assert [r[0] for r in selected] == [r[0] for r in expected[1:]]
    assert aliases.summary()["group_count"] == 2
    assert aliases.summary()["passage_count"] == 1
