import json
import sqlite3
from collections import defaultdict
from types import SimpleNamespace

import joblib
import numpy as np
import pytest
from vibechecker_engine.deep import DEEP_FEATURE_NAMES, DeepExtractor, DeepModel, ProbeDeepStacker
from vibechecker_engine.signals import ENCODER_VECTOR_VERSION
from vibechecker_eval import band_controls, rewrite_refit, rewrite_sidecar
from vibechecker_eval.deep_runner import evaluation_training_scope
from vibechecker_eval.loaders import fingerprint
from vibechecker_eval.refit import CachedRow, append_probe, validation_quality
from vibechecker_eval.refit_cache import CALIBRATION, TRAIN, VALIDATION
from vibechecker_eval.registry import sha256
from vibechecker_eval.rewrite_data import RewriteDocument, RewritePair
from vibechecker_eval.rewrite_refit import admissibility, sensitivity, stress_metrics
from vibechecker_eval.rewrite_sidecar import DOMAINS, ROLES, STRESS, select_pairs, sidecar_rows

RUNTIME = {"engine_source_sha256": "a" * 64, "packages": {"numpy": "fixture"}}


class KnownProbe:
    classes_ = np.array([0, 1])
    n_features_in_ = 769

    def __init__(self, provenance, informative):
        self.training_provenance_ = provenance
        self.informative = informative

    def predict_proba(self, x):
        prob = (
            np.where(np.asarray(x)[:, 0] > 0, 0.95, 0.05)
            if self.informative
            else np.full(len(x), 0.5)
        )
        return np.column_stack([1 - prob, prob])


def test_real_stacker_refit_selects_on_validation_and_replays_incumbent_on_band_rejection(
    tmp_path, monkeypatch
):
    enc = {"model.safetensors": "1" * 64}
    identity = {k: enc for k in ("LM", "ENCODER", "PAIR_OBSERVER", "PAIR_PERFORMER")}
    scope = {"weights": identity, "manifest": {"raid": "pin"}, "commercial_only": False}
    aliases = {"sha256": "2" * 64}
    p = {
        "partition": "train",
        "head_fold": 0,
        "commercial_only": False,
        "encoder_sha256": enc["model.safetensors"],
        "encoder_files": enc,
        "backend": "mlx-metal",
        "quick_prefill": 512,
        "manifest": scope["manifest"],
        "source_aliases": aliases,
        "vector_version": ENCODER_VECTOR_VERSION,
        "seed": 42,
        "fit_counts": {"human": 20, "machine": 20},
        "fit_document_ids_sha256": "3" * 64,
        "fit_group_ids_sha256": "4" * 64,
    }
    source_probe = KnownProbe(p, False)
    signed = {"selection_sha256": "5" * 64}
    role_proof = {
        role: {
            "groups": 12,
            "documents": 24,
            "group_ids_sha256": fingerprint(role + "/groups"),
            "document_ids_sha256": fingerprint(role + "/docs"),
        }
        for role in ("fit", "calibration", "development")
    }
    candidate = KnownProbe(
        {
            **p,
            "selection": {"selected": "mixture"},
            "rewrite_supplement": {
                "scheme": "rewrite-origin-paired-paraphrase-v1",
                "role": "head",
                "commercial_only": False,
                "cohort": signed,
                "supervised_roles": role_proof,
                "paired_roles": role_proof,
            },
        },
        True,
    )

    def rows(part, tag, n):
        return [
            CachedRow(
                f"{tag}-{part}-{i}",
                f"{tag}-{part}-{i // 2}",
                part,
                i % 2,
                350,
                ("genre/essay", "generator/machine" if i % 2 else "generator/human"),
                np.zeros(len(DEEP_FEATURE_NAMES)),
                np.full(769, i % 2),
            )
            for i in range(n)
        ]

    base = {r: rows(r, "ordinary", 40) for r in (TRAIN, CALIBRATION, VALIDATION)}
    extra = {r: rows(r, "paired", 12) for r in (TRAIN, CALIBRATION, STRESS)}
    domains = {r.group: DOMAINS[(i // 2) % 2] for i, r in enumerate(extra[STRESS])}
    x = append_probe(
        np.stack([r.features for r in base[TRAIN]]),
        np.stack([r.encoder for r in base[TRAIN]]),
        source_probe,
    )
    y = np.array([r.label for r in base[TRAIN]])
    old = DeepModel(
        None,
        ProbeDeepStacker.fit(x, y, x, y, [350] * len(y), seed=42, probe_anchor=0.75),
        identity,
        source_probe,
    )
    old.training_scope = scope
    old.fit_selection = {"quick_prefill": 512}
    old.fit_counts = {}
    old.refit_provenance = {"probe_sha256": "8" * 64, "source_aliases": aliases}
    args = SimpleNamespace(
        incumbent=tmp_path / "v2.joblib",
        sidecar=tmp_path / "pairs.sqlite",
        probe=[tmp_path / "probe.joblib"],
        selection_out=tmp_path / "report.json",
        model_out=tmp_path / "selected.joblib",
        band_controls=tmp_path / "bands.sqlite",
        supplement_sha256="9" * 64,
    )
    args.band_controls.write_bytes(b"fixture independent controls")
    args.band_controls_sha256 = sha256(args.band_controls)
    old.save(args.incumbent)
    joblib.dump(candidate, args.probe[0])
    args.probe_sha256 = [sha256(args.probe[0])]
    reference = validation_quality(old.stacker, x, base[VALIDATION], {})
    selection = {
        "validation_cohort": {"scored_ids_sha256": reference["scored_ids_sha256"]},
        "selected": "winner",
        "candidates": {"winner": reference},
    }
    info = {
        "runtime": RUNTIME,
        "seed": 42,
        "backend": "mlx-metal",
        "quick_prefill": 512,
        "encoder_vector": ENCODER_VECTOR_VERSION,
        "training_scope": scope,
    }
    protocol = {
        "supplement": signed,
        "selection_sha256": "a" * 64,
        "incumbent_sha256": sha256(args.incumbent),
    }
    monkeypatch.setattr(
        rewrite_refit,
        "inputs",
        lambda args: (old, old, selection, info, base, {}, protocol, {}, {"id"}, {"group"}),
    )
    monkeypatch.setattr(
        rewrite_refit,
        "sidecar_rows",
        lambda *a: (
            extra,
            domains,
            {"matched_documents": {}, "content_sha256": "b" * 64, "runtime": RUNTIME},
        ),
    )

    def controls(
        path,
        *,
        expected_sha256,
        parent,
        parent_sha256,
        excluded_ids,
        excluded_groups,
        expected_runtime,
    ):
        assert expected_sha256 == args.band_controls_sha256 and parent_sha256 == sha256(
            args.incumbent
        )
        assert excluded_ids == {"id"} and excluded_groups == {"group"}
        assert expected_runtime == RUNTIME
        return SimpleNamespace(provenance={"runtime": RUNTIME})

    monkeypatch.setattr(band_controls, "load_band_controls", controls)
    monkeypatch.setattr(rewrite_refit, "verified_study", lambda *a: {"qualified": "mixture"})
    monkeypatch.setattr(
        band_controls,
        "calibrate_high_band",
        lambda stacker, probe, controls: {"fit": "independent"},
    )
    result = rewrite_refit.fit(args)
    report = json.loads(args.selection_out.read_bytes())
    assert result["selected"].startswith("mixture") and result["candidates"] == 4
    fitted = DeepModel.load(args.model_out)
    assert fitted.training_scope["supplements"] == report["training_supplements"]
    assert evaluation_training_scope(fitted, scope) == (True, report["training_supplements"])
    with pytest.raises(ValueError, match="research licensing"):
        evaluation_training_scope(fitted, {**scope, "commercial_only": True})
    assert fitted.refit_provenance["supplements_sha256"] == rewrite_sidecar.metadata_hash(
        fitted.training_scope["supplements"]
    )
    fitted.refit_provenance["supplements_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="research licensing"):
        evaluation_training_scope(fitted, scope)
    for name, q in report["candidates"].items():
        assert q["ordinary"]["scored_ids_sha256"] == reference["scored_ids_sha256"]
        assert q["stress"]["strata"]["books"]["groups"] == 3
        assert q["sensitivity_after"]["total"] == 20
        assert bool(q["exclusions"]) == name.startswith("ordinary-control")

    def refuse(*a):
        raise ValueError("Unattainable high band")

    monkeypatch.setattr(band_controls, "calibrate_high_band", refuse)
    args.probe = []
    args.probe_sha256 = []
    fallback = rewrite_refit.fit(args)
    assert fallback["selected"] == "incumbent" and fallback["candidates"] == 2
    failed = json.loads(args.selection_out.read_bytes())["candidates"]
    assert all(q["sensitivity_after"] is None and q["stress"] for q in failed.values())
    assert args.model_out.read_bytes() == args.incumbent.read_bytes()


def test_probe_provenance_rejects_repeated_and_nonhex_role_digests_and_false_membership(
    tmp_path, monkeypatch
):
    from copy import deepcopy
    from pathlib import Path

    from vibechecker_eval import rewrite_data

    reports = Path(__file__).resolve().parents[1] / "reports" / "phase-1"
    args = SimpleNamespace(
        probe_study=reports / "rewrite-origin-probe.json",
        probe_membership=reports / "rewrite-origin-membership.json",
        supplement=tmp_path / "synthetic",
    )
    args.probe_membership_sha256 = sha256(args.probe_membership)
    study = json.loads(args.probe_study.read_bytes())
    audit = json.loads(args.probe_membership.read_bytes())
    args.supplement_sha256 = audit["authenticated_cohort_db_sha256"]
    p = study["provenance"]
    aliases = p["source_aliases"]
    supplement = p["rewrite_supplement"]["cohort"]
    info = {
        "encoder_vector": p["vector_version"],
        "backend": p["backend"],
        "quick_prefill": p["quick_prefill"],
        "training_scope": {
            "weights": {"ENCODER": p["encoder_files"]},
            "manifest": p["manifest"],
            "commercial_only": False,
        },
    }
    assert rewrite_refit.validate_rewrite_probe(KnownProbe(p, True), info, aliases, supplement) == p
    for value in ("g" * 64, audit["paired_roles"]["fit"]["group_ids_sha256"]):
        broken = deepcopy(p)
        broken["rewrite_supplement"]["paired_roles"]["calibration"]["group_ids_sha256"] = value
        with pytest.raises(ValueError, match="membership"):
            rewrite_refit.validate_rewrite_probe(
                KnownProbe(broken, True), info, aliases, supplement
            )
    false_pairs = fixture_pairs()["head"]
    monkeypatch.setattr(rewrite_data, "load_rewrite_pairs", lambda *a, **k: false_pairs)
    incumbent = SimpleNamespace(
        probe=SimpleNamespace(
            training_provenance_={
                "fit_document_ids_sha256": audit["original_general"]["document_ids_sha256"],
                "fit_group_ids_sha256": audit["original_general"]["group_ids_sha256"],
            }
        )
    )
    with pytest.raises(ValueError, match="membership|Authenticated"):
        rewrite_refit.verified_study(args, study["model_sha256"], p, incumbent)


def fixture_pairs():
    by_role = defaultdict(list)
    for role in ROLES:
        for domain in DOMAINS:
            for index in range(3):
                g = f"raid:{role}-{domain}-{index}"

                def doc(tag, group=g):
                    text = f"{group} {tag}"
                    return RewriteDocument(
                        fingerprint(text),
                        "publisher-id",
                        "parent-id",
                        text,
                        "human" if "human" in tag else "model",
                        350,
                    )

                by_role[role].append(
                    RewritePair(
                        g,
                        role,
                        domain,
                        doc("human"),
                        doc("machine"),
                        doc("clean_human"),
                        doc("clean_machine"),
                    )
                )
    return by_role


def test_source_isolation_keeps_matched_origins_and_frozen_roles():
    by_role = fixture_pairs()
    old = defaultdict(lambda: (set(), set()))
    protected = by_role["stress"][0]
    old["protected"][0].add(protected.clean_human.id)
    old["stack"][1].add(fingerprint(by_role["stress"][1].source_group))
    old["calibration"][0].add(by_role["calibration"][0].machine.id)
    chosen, excluded, all_ids, all_groups = select_pairs(by_role, old, 2, 42)
    assert len(chosen) == 11
    assert protected not in chosen and by_role["stress"][1] not in chosen
    assert all(p.role != "head" for p in chosen)
    assert protected.clean_human.id in all_ids and fingerprint(protected.source_group) in all_groups
    assert excluded["stress/books/cross_role"] == 2
    assert excluded["calibration/books/already_cached"] == 1
    reversed_input = {k: list(reversed(v)) for k, v in by_role.items()}
    assert chosen == select_pairs(reversed_input, old, 2, 42)[0]
    old["protected"][1].add(fingerprint(by_role["head"][0].source_group))
    with pytest.raises(ValueError, match="probe head role"):
        select_pairs(by_role, old, 2, 42)


def test_interrupted_sidecar_resumes_and_omits_entire_refused_pair(tmp_path, monkeypatch):
    from vibechecker_engine.text import Refusal

    by_role = fixture_pairs()
    pairs = select_pairs(by_role, defaultdict(lambda: (set(), set())), 2, 42)[0]
    members = {}
    for pair in pairs:
        for label, d in enumerate((pair.human, pair.machine)):
            members[d.id] = (fingerprint(pair.source_group), pair.role, pair.domain, label, d)
    args = SimpleNamespace(sidecar=tmp_path / "numeric.sqlite")
    scope = {
        "base_runtime": RUNTIME,
        "feature_names": DEEP_FEATURE_NAMES,
        "backend": "mlx-metal",
        "quick_prefill": 512,
        "selection_sha256": "f" * 64,
    }
    scope["feature_names"] = list(scope["feature_names"])
    parent = SimpleNamespace(
        verify=lambda x: None,
        heads=SimpleNamespace(features=lambda raw: [1.0] * len(DEEP_FEATURE_NAMES)),
    )
    monkeypatch.setattr(
        rewrite_sidecar,
        "inputs",
        lambda a: (parent, None, None, None, None, None, scope, members, None, None),
    )
    refused = pairs[-1].human
    seen = []

    def extract(text):
        seen.append(text)
        if len(seen) == 3:
            raise KeyboardInterrupt
        if text == refused.text:
            raise Refusal("not_english")
        return SimpleNamespace(encoder_vector=np.zeros(769))

    fake = SimpleNamespace(
        backend="mlx-metal",
        quick=SimpleNamespace(lm=SimpleNamespace(chunk_size=512)),
        extract=extract,
    )
    monkeypatch.setattr(DeepExtractor, "from_env", lambda **kwargs: fake)
    monkeypatch.setattr(
        rewrite_sidecar, "runtime_identity", lambda: {**RUNTIME, "engine_source_sha256": "e" * 64}
    )
    with pytest.raises(ValueError, match="original numeric runtime"):
        rewrite_sidecar.collect(args)
    monkeypatch.setattr(rewrite_sidecar, "runtime_identity", lambda: RUNTIME)
    with pytest.raises(KeyboardInterrupt):
        rewrite_sidecar.collect(args)
    with pytest.raises(ValueError, match="completed"):
        sidecar_rows(args.sidecar, scope, members)
    assert rewrite_sidecar.collect(args)["resumed"] == 2
    assert rewrite_sidecar.collect(args)["resumed"] == len(members)
    accepted, domains, summary = sidecar_rows(args.sidecar, scope, members)
    assert len(domains) >= len(pairs) - 1
    assert sum(map(len, accepted.values())) == len(members) - 2
    assert sum(summary["document_refusals"].values()) == 1
    assert all(
        r.group != fingerprint(pairs[-1].source_group) for rows in accepted.values() for r in rows
    )
    with sqlite3.connect(args.sidecar) as db:
        assert len(
            db.execute("SELECT features FROM docs WHERE features IS NOT NULL LIMIT 1").fetchone()[0]
        ) == 8 * len(DEEP_FEATURE_NAMES)
        db.execute("UPDATE docs SET source='wrong group' WHERE id=?", (refused.id,))
    with pytest.raises(ValueError, match="membership differs"):
        sidecar_rows(args.sidecar, scope, members)


def test_matched_metrics_keep_ties_tiny_strata_and_preserve_high_band():
    rows = [CachedRow(str(i), str(i // 2), STRESS, i % 2, 350, (), None, None) for i in range(4)]
    domains = {"0": "books", "1": "news"}
    baseline = stress_metrics([50, 50, 90, 10], rows, domains)
    better = stress_metrics([5, 95, 50, 50], rows, domains)
    assert better["strata"]["pooled"]["pair_concordance"] == 0.75
    assert better["strata"]["news"]["ties"] == 1 and better["strata"]["news"]["groups"] == 1
    assert better["strata"]["books"]["machine"]["count"] == 1
    q = {"worst_stratum_ece": 0.09, "gates": {"checks": {"pooled_ece": {"status": "pass"}}}}
    s = sensitivity([5, 95, 50, 50], [0, 1, 0, 1], 50)
    incumbent = {"stress": baseline, "sensitivity": s, "ordinary": {**q, "worst_stratum_ece": 0.5}}
    assert not admissibility(q, better, s, s, incumbent)
    assert admissibility(q, baseline, s, s, incumbent)
    assert admissibility(q, better, s, {**s, "threshold": 101, "hits": 0}, incumbent)
    assert admissibility(
        {**q, "gates": {"checks": {"pooled_ece": {"status": "fail"}}}}, better, s, s, incumbent
    )
