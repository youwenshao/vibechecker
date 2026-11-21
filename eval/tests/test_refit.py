import json
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import joblib
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from vibechecker_engine.deep import DEEP_FEATURE_NAMES, DeepExtractor, DeepModel, DeepStacker
from vibechecker_engine.signals import ENCODER_VECTOR_VERSION
from vibechecker_engine.text import count_words
from vibechecker_eval import refit, refit_cache
from vibechecker_eval.cli import main
from vibechecker_eval.deep_cohort import fold
from vibechecker_eval.loaders import Example, fingerprint
from vibechecker_eval.refit import run_refit, validate_probe
from vibechecker_eval.refit_cache import CALIBRATION, TRAIN, VALIDATION, collect, plan_rows, role
from vibechecker_eval.registry import registry, sha256
from vibechecker_eval.runner import sample
from vibechecker_eval.source_groups import human_source_aliases


class NumericHeads:
    def features(self, raw):
        return raw.features


def corpus():
    result = []
    for split in ("train", "calibration", "test"):
        for i in range(40):
            for y in (0, 1):
                tag = "robot" if y else "human"
                doc = (
                    f"{tag} Private-text-marker {split} {i}. "
                    + "This town keeps the library open. " * 55
                )
                source = "raid-attacks" if i % 3 == 0 else "raid"
                result.append(
                    Example(
                        doc,
                        y,
                        source,
                        split,
                        "essay",
                        writer="ESL" if i % 2 == 0 and not y else "unknown",
                        generator=f"model-{i % 5}" if y else "human",
                        attack="rewrite" if i % 3 == 0 else "none",
                        source_group=f"{split}-{i}",
                    )
                )
    return result


def arguments(tmp_path):
    return SimpleNamespace(
        model_in=tmp_path / "parent.joblib",
        features=tmp_path / "features.sqlite",
        cache=tmp_path,
        seed=42,
        limit_per_class=20,
        train_limit_per_class=14,
        cal_limit_per_class=18,
        attack_limit_per_class=4,
        without_encoder_vectors=False,
        commercial_only=False,
        probe=None,
        model_out=tmp_path / "winner.joblib",
        selection_out=tmp_path / "scores.json",
    )


def test_group_stratification_quarantines_raw_cross_split_duplicates_and_preserves_validation(
    tmp_path, monkeypatch
):
    args = arguments(tmp_path)
    rows = corpus()
    train = next(r for r in rows if role(r) == TRAIN)
    conflicting = next(r for r in rows if role(r) == CALIBRATION)
    rows += [
        replace(train, split="test", dataset="liang"),
        replace(conflicting, text="Held out. " * 310, split="test"),
    ]
    monkeypatch.setattr(refit_cache, "examples", lambda datasets, cache: iter(rows))
    planned = plan_rows(args, [], count_words)
    assert fingerprint(train.text) not in planned
    assert all(
        item.source_group != conflicting.source_group
        for _, part, item, _ in planned.values()
        if part in (TRAIN, CALIBRATION)
    )
    expected = {
        fingerprint(r.text)
        for r, _ in sample(
            rows, args.limit_per_class, args.seed, count_words, length_range=(300, 2500)
        )[0]
        if r.split == "test" and fold(r, "bakeoff") == 0
    }
    assert expected == {k for k, (_, part, _, _) in planned.items() if part == VALIDATION}
    seen = set()
    for group, part, item, _ in planned.values():
        if part != VALIDATION:
            key = (part, item.dataset, item.label, group)
            assert key not in seen
            seen.add(key)
            assert part == CALIBRATION or (item.split == "train" and fold(item, "head") == 1)
    assert (
        sum(1 for part, source, y, _ in seen if (part, source, y) == (TRAIN, "raid-attacks", 1))
        <= 4
    )


@pytest.fixture
def cached_probe(tmp_path, monkeypatch):
    datasets = [registry()[k] for k in ("raid", "raid-attacks")]
    args = arguments(tmp_path)
    rows = corpus()
    monkeypatch.setattr(refit_cache, "examples", lambda datasets, cache: iter(rows))
    monkeypatch.setattr(refit, "examples", lambda datasets, cache: iter(rows))
    selected = plan_rows(args, datasets, count_words)
    args.ambiguous_group = {}
    for part in (TRAIN, CALIBRATION, VALIDATION):
        derivative = next(
            r for _, role_id, r, _ in selected.values() if role_id == part and r.label
        )
        rows.append(replace(derivative, text="One shared human source", label=0, generator="human"))
        args.ambiguous_group[part] = fingerprint(derivative.source_group)
    aliases = human_source_aliases(rows).summary()
    assert aliases["group_count"] == 3
    identity = {
        name: {"model.safetensors": "a" * 64}
        for name in ("LM", "ENCODER", "PAIR_OBSERVER", "PAIR_PERFORMER")
    }
    manifest = {
        d.id: {"version": d.version, "sha256": [a.sha256 for a in d.artifacts]} for d in datasets
    }
    y = np.tile([0, 1], 25)
    # The parent has a deliberately uninformative feature fit.
    x = np.ones((len(y), len(DEEP_FEATURE_NAMES)))
    old = DeepModel(NumericHeads(), DeepStacker.fit(x, y, x, y, [350] * len(y)), identity)
    old.training_scope = {
        "manifest": manifest,
        "dataset_order": [d.id for d in datasets],
        "weights": identity,
        "commercial_only": False,
    }
    old.save(args.model_in)
    calls = []

    class Extractor:
        backend = "mlx-cpu"

        def extract(self, text):
            calls.append(fingerprint(text))
            if len(calls) == 3:
                raise KeyboardInterrupt
            pos = float(text.startswith("robot"))
            vector = np.full(769, pos, dtype=np.float32)
            return SimpleNamespace(
                features=np.zeros(len(DEEP_FEATURE_NAMES)), encoder_vector=vector
            )

    extractor = Extractor()
    extractor.identity = identity
    extractor.quick = SimpleNamespace(lm=SimpleNamespace(chunk_size=256))
    monkeypatch.setattr(DeepExtractor, "from_env", lambda **kwargs: extractor)

    with pytest.raises(KeyboardInterrupt):
        collect(args, datasets)
    with pytest.raises(ValueError, match="Incomplete"):
        run_refit(args)
    completed = collect(args, datasets)
    assert completed["resumed"] == 2 and completed["accepted"] == completed["selected"]
    assert collect(args, datasets)["resumed"] == completed["selected"]
    assert b"Private-text-marker" not in args.features.read_bytes()
    with sqlite3.connect(args.features) as db:
        info = json.loads(db.execute("SELECT value FROM meta WHERE key='provenance'").fetchone()[0])
        assert db.execute("SELECT COUNT(DISTINCT role) FROM documents").fetchone()[0] == 3
    altered = SimpleNamespace(**{**vars(args), "seed": 6})
    with pytest.raises(ValueError, match="provenance differs"):
        collect(altered, datasets)

    probe = LogisticRegression().fit(np.vstack([np.full(769, y_i, dtype=float) for y_i in y]), y)
    probe.training_provenance_ = {
        "partition": "train",
        "head_fold": 0,
        "seed": 42,
        "fit_counts": {"0": 25, "1": 25},
        "encoder_sha256": "a" * 64,
        "encoder_files": identity["ENCODER"],
        "backend": extractor.backend,
        "source_aliases": aliases,
        "quick_prefill": 256,
        "manifest": manifest,
        "commercial_only": False,
        "vector_version": ENCODER_VECTOR_VERSION,
        "fit_group_ids_sha256": "c" * 64,
        "fit_document_ids_sha256": "d" * 64,
    }
    original = probe.training_provenance_
    for corrupt in (
        {"quick_prefill": 64},
        {"partition": "test"},
        {"encoder_files": {}},
        {"head_fold": 1},
        {"source_aliases": None},
        {"source_aliases": {**aliases, "sha256": "1" * 64}},
    ):
        probe.training_provenance_ = {**original, **corrupt}
        with pytest.raises(ValueError, match="Probe"):
            validate_probe(probe, info, aliases)
    for probe_backend, cache_backend in (
        ("torch-cuda", extractor.backend),
        (None, extractor.backend),
        (extractor.backend, None),
        (None, None),
        ("", ""),
        (" ", " "),
    ):
        cache_info = dict(info)
        if cache_backend is None:
            cache_info.pop("backend")
        else:
            cache_info["backend"] = cache_backend
        probe.training_provenance_ = {**original, "backend": probe_backend}
        if probe_backend is None:
            probe.training_provenance_.pop("backend")
        with pytest.raises(ValueError, match="same training backend"):
            validate_probe(probe, cache_info, aliases)
    probe.training_provenance_ = original
    args.probe = tmp_path / "probe.joblib"
    joblib.dump(probe, args.probe)
    return args


def test_resumable_private_cache_cpu_probe_selection_and_compatible_model(cached_probe):
    args = cached_probe
    cache_sha = sha256(args.features)
    outcome = run_refit(args)
    report = json.loads(args.selection_out.read_bytes())
    assert outcome["selected"] != "original" and report["cohort"] == "validation"
    assert "probe-leaves7-anchor0.75" in report["candidates"]
    assert (
        report["candidates"][outcome["selected"]]["worst_stratum_ece"]
        < report["candidates"]["original"]["worst_stratum_ece"]
    )
    fitted = DeepModel.load(args.model_out)
    assert fitted.training_scope == DeepModel.load(args.model_in).training_scope
    assert fitted.refit_provenance["frozen_parent_sha256"] == sha256(args.model_in)
    quarantine = report["source_quarantine"]
    assert sha256(args.features) == cache_sha
    assert quarantine["source_aliases"] == fitted.probe.training_provenance_["source_aliases"]
    assert quarantine["source_aliases"] == fitted.refit_provenance["source_aliases"]
    assert (
        quarantine["effective_selection_sha256"]
        == fitted.refit_provenance["effective_selection_sha256"]
    )
    with sqlite3.connect(args.features) as db:
        for part, name in (
            (TRAIN, "train"),
            (CALIBRATION, "calibration"),
            (VALIDATION, "validation"),
        ):
            cached = list(
                db.execute(
                    "SELECT id,group_id FROM documents WHERE role=? AND refusal IS NULL ORDER BY id",
                    (part,),
                )
            )
            matching = [key for key, group in cached if group == args.ambiguous_group[part]]
            expected = [
                key
                for key, group in cached
                if group != args.ambiguous_group[part] or part == VALIDATION
            ]
            assert quarantine["effective"][name][
                "document_ids_sha256"
            ] == refit_cache.digest_strings(expected)
            assert len(expected) == report["counts"][str(part)]["documents"]
            if part == VALIDATION:
                affected = quarantine["validation_aliases_retained"]
            else:
                affected = quarantine["excluded"][name]
            assert len(matching) == affected["documents"] > 0
            assert affected["document_ids_sha256"] == refit_cache.digest_strings(matching)
            assert affected["group_ids_sha256"] == refit_cache.digest_strings(
                [args.ambiguous_group[part]]
            )
    assert (
        report["probe_training_provenance"]
        == report["probes"][sha256(args.probe)]["training_provenance"]
    )
    assert "Private-text-marker" not in args.selection_out.read_text()


def test_alias_scan_rejects_a_changed_dataset_manifest_before_reading(tmp_path):
    scope = {
        "dataset_order": ["raid"],
        "commercial_only": False,
        "manifest": {"raid": {"version": "different", "sha256": ["0" * 64]}},
    }
    with pytest.raises(ValueError, match="original pinned dataset manifest"):
        refit.eligible_fit_rows({"training_scope": scope}, {}, tmp_path)


def test_two_probes_share_validation_matrices_and_parent_fallback(
    cached_probe, tmp_path, monkeypatch
):
    args = cached_probe
    first = args.probe
    alias = tmp_path / "copy.joblib"
    alias.write_bytes(first.read_bytes())
    second = tmp_path / "alternate.joblib"
    y = np.tile([0, 1], 20)
    other = LogisticRegression(C=0.3).fit(np.vstack([np.full(769, 1 - label) for label in y]), y)
    other.training_provenance_ = {
        **joblib.load(first).training_provenance_,
        "seed": 17,
        "fit_counts": {"0": 20, "1": 20},
        "fit_document_ids_sha256": "e" * 64,
    }
    joblib.dump(other, second)
    predict = LogisticRegression.predict_proba
    predicted = []

    def counted(probe, values):
        predicted.append(probe.training_provenance_["seed"])
        return predict(probe, values)

    monkeypatch.setattr(LogisticRegression, "predict_proba", counted)
    assert (
        main(
            [
                "deep-refit",
                "--model-in",
                str(args.model_in),
                "--features",
                str(args.features),
                "--model-out",
                str(args.model_out),
                "--selection-out",
                str(args.selection_out),
                "--probe",
                str(second),
                "--probe",
                str(first),
                "--probe",
                str(alias),
            ]
        )
        == 0
    )
    # Each independent probe computes probabilities once on each of three partitions.
    assert sorted(predicted) == [17] * 3 + [42] * 3
    report = json.loads(args.selection_out.read_bytes())
    assert report["cohort"] == "validation"
    assert len(report["candidates"]) == 11
    assert set(report["probes"]) == {sha256(first), sha256(second)}
    assert set(report["probes"][sha256(first)]["artifact_names"]) == {first.name, alias.name}
    assert report["probes"][sha256(second)]["training_provenance"] == other.training_provenance_
    winning_sha = report["lineage"]["probe_sha256"]
    assert winning_sha == sha256(first)
    assert (
        DeepModel.load(args.model_out).probe.training_provenance_
        == report["probes"][winning_sha]["training_provenance"]
    )
    with sqlite3.connect(args.features) as db:
        ids = [
            r[0]
            for r in db.execute(
                "SELECT id FROM documents WHERE role=? AND refusal IS NULL ORDER BY id",
                (VALIDATION,),
            )
        ]
    fixed = fingerprint(" ".join(ids))
    assert report["validation_cohort"]["scored_ids_sha256"] == fixed
    assert report["validation_cohort"]["documents"] == len(ids)
    assert {r["scored_ids_sha256"] for r in report["candidates"].values()} == {fixed}
    for digest, entry in report["probes"].items():
        configs = set()
        ratios = []
        for candidate in entry["candidates"]:
            evidence = report["candidates"][candidate]
            settings = evidence["settings"]
            assert settings["probe_sha256"] == digest
            configs.add((settings["max_leaf_nodes"], settings["probe_anchor"]))
            ratios.append(evidence["minimax_gate_ratio"])
            assert ratios[-1] == pytest.approx(
                max(evidence["pooled_ece"] / 0.05, evidence["worst_stratum_ece"] / 0.08)
            )
        assert configs == {(31, 0), (7, 0), (7, 0.5), (7, 0.75)}
        assert min(ratios) == entry["minimax_gate_ratio"]
        assert (
            entry["best_admissible_candidate"] is None
            or entry["best_admissible_candidate"] in entry["candidates"]
        )

    args.probe = [first, second]
    original = report["candidates"]["original"]
    monkeypatch.setattr(refit, "validation_quality", lambda *a: original.copy())
    assert run_refit(args)["selected"] == "original"
    assert sha256(args.model_out) == sha256(args.model_in)

    def mismatched(stacker, matrix, rows, names):
        q = original.copy()
        if matrix.shape[1] > len(DEEP_FEATURE_NAMES):
            q["scored_ids_sha256"] = "0" * 64
        return q

    monkeypatch.setattr(refit, "validation_quality", mismatched)
    with pytest.raises(ValueError, match="identical reserved validation documents"):
        run_refit(args)
    assert sha256(args.model_out) == sha256(args.model_in)


def test_fixed_probe_anchor_is_applied_before_calibration():
    from scipy.special import expit, logit
    from vibechecker_engine.deep import ProbeDeepStacker
    from vibechecker_engine.stacker import ProbeAnchoredClassifier

    y = np.tile([0, 1], 32)
    x = np.random.default_rng(7).normal(size=(len(y), len(ProbeDeepStacker.FEATURES)))
    x[:, -1] = np.where(y, 0.9, 0.1)
    m = ProbeDeepStacker.fit(
        x, y, x, y, [400] * len(y), max_leaf_nodes=7, l2_regularization=1, probe_anchor=0.75
    )
    assert isinstance(m.classifier, ProbeAnchoredClassifier)
    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=1):
        raw = m.classifier.estimator.decision_function(x)
        np.testing.assert_allclose(
            m.classifier.predict_proba(x)[:, 1], expit(0.25 * raw + 0.75 * logit(x[:, -1]))
        )
    assert len(m.calibrators["pooled"].bootstrap) == 200
    assert len(m.predict(x[0], 400)["signals"]) == 8
