import json
import sqlite3

import numpy as np
import pytest
from vibechecker_eval import academic_intake
from vibechecker_eval.academic_addition import read_academic
from vibechecker_eval.academic_features import verify_cache
from vibechecker_eval.loaders import fingerprint
from vibechecker_eval.registry import sha256


def test_matching_preserves_common_fields_and_maximum_cardinality():
    machines = [
        {"id": "m-short", "words": 320, "subject": "cs"},
        {"id": "m-long", "words": 400, "subject": "cs"},
        {"id": "unknown", "words": 380, "subject": None},
    ]
    humans = [
        {"id": "h-early", "words": 300, "subject": "cs"},
        {"id": "h-late", "words": 480, "subject": "cs"},
        {"id": "different", "words": 375, "subject": "biology"},
    ]

    def pairs(a, b):
        return {(left["id"], right["id"]) for left, right in academic_intake.match_role(a, b)}

    assert (
        pairs(machines, humans)
        == pairs(machines[::-1], humans[::-1])
        == {("m-short", "h-early"), ("m-long", "h-late")}
    )


def test_frozen_projection_requires_independent_human_common_support(tmp_path, monkeypatch):
    paths = {
        k: tmp_path / k
        for k in (
            "subjects",
            "machine_manifest",
            "machine_projection",
            "human_projection",
            "human_manifest",
        )
    }
    for p in paths.values():
        p.write_text("{}")
    scopes = {
        "scheme": "pre2020-academic-human-reference-v1",
        "isolation": dict.fromkeys(academic_intake.ISOLATION, 0),
    }

    def doc(key, gen):
        return {"id": fingerprint(key), "words": 375, "generator": gen, "text": key}

    def row(key, role, label):
        base = {
            "role": role,
            "source_group": key,
            "group": fingerprint(key),
            "target_label": label,
            "domain": "abstracts",
            "child": doc("passage-" + key, "generated" if label else "human"),
        }
        if label:
            return {
                **base,
                "clean_human": doc("h-" + key, "human"),
                "clean_machine": doc("m-" + key, "generated"),
            }
        return {
            **base,
            "source": "papers",
            "license": "CC BY",
            "transformation": "native",
            "year": 2016,
            "subject": "CS",
        }

    machine = [row("m-" + p, p, 1) for p in academic_intake.FIT_ROLES]
    human = [row("h-" + p, p, 0) for p in (*academic_intake.FIT_ROLES, academic_intake.HUMAN_DEV)]
    mapping = {
        "machine_projection_sha256": sha256(paths["machine_projection"]),
        "groups": {
            r["group"]: {"subject": "CS", "evidence": "publisher category listing"} for r in machine
        },
    }
    paths["subjects"].write_text(json.dumps(mapping))
    monkeypatch.setattr(
        academic_intake,
        "projection",
        lambda p, side: ({}, machine) if side == "machine" else (scopes, human),
    )
    monkeypatch.setattr(academic_intake, "verify_machine", lambda *_: None)
    monkeypatch.setattr(academic_intake, "verified_doc", lambda *_, **kw: None)
    monkeypatch.setattr(academic_intake, "protected_keys", lambda _: (set(), set()))
    rows, summary = academic_intake.project(paths)
    assert summary["ready"] and len(rows) == 5
    human[-1]["subject"] = "no common topic"
    assert not academic_intake.project(paths)[1]["ready"]
    human[-1]["year"] = 2022
    with pytest.raises(ValueError, match="date"):
        academic_intake.project(paths)
    human[-1]["year"] = 2016
    monkeypatch.setattr(
        academic_intake, "protected_keys", lambda _: ({machine[0]["clean_machine"]["id"]}, set())
    )
    with pytest.raises(ValueError, match="overlap"):
        academic_intake.project(paths)


def test_opaque_cache_role_and_binding(tmp_path):
    path = tmp_path / "features.sqlite"
    member = {
        "id": "a",
        "group": "g",
        "kind": "native_human",
        "domain": "abstract",
        "generator": "human",
        "words": 330,
        "label": 0,
        "role": academic_intake.HUMAN_DEV,
        "source": "science",
        "subject": "cs",
    }
    provenance = {"selection_sha256": "bound"}
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE meta(provenance,complete,content_sha256)")
        db.execute(
            "CREATE TABLE documents(rowno,id,source,kind,domain,generator,words,features,encoder)"
        )
        db.execute(
            "INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?)",
            (
                0,
                "a",
                "g",
                "native_human",
                "abstract",
                "human",
                330,
                np.zeros(13, "<f8").tobytes(),
                np.zeros(769, "<f4").tobytes(),
            ),
        )
        _, digest, _ = verify_cache(db, [member], complete=True)
        db.execute("INSERT INTO meta VALUES(?,?,?)", (json.dumps(provenance), 1, digest))
    receipt = {"provenance": provenance, "sidecar_sha256": sha256(path), "content_sha256": digest}
    plan = {"members": [member], "selection_sha256": "bound"}
    rows, groups = read_academic(path, receipt, plan)
    assert len(groups["pooled"]) == 1 and all(r.label == 0 for v in rows.values() for r in v)
    member["words"] = 340
    with pytest.raises(ValueError, match="word counts"):
        read_academic(path, receipt, plan)


def test_fixed_academic_sensitivity_and_native_specificity_guards():
    from vibechecker_eval.academic_addition import academic_admissibility
    from vibechecker_eval.metrics import rate

    def machine(rewrites, parents):
        return {
            "academic/rewrite": {"high_detection": rate(rewrites, 66)},
            "academic/original_clean": {"high_detection": rate(parents, 54)},
        }

    def native(hits):
        return {"pooled": {"high_false_positive": rate(hits, 3)}}

    assert academic_admissibility(machine(60, 49), native(0), machine(66, 54), native(0)) == []
    rejected = academic_admissibility(machine(59, 48), native(1), machine(66, 54), native(0))
    assert len(rejected) == 3
    with pytest.raises(ValueError, match="same independent"):
        academic_admissibility(
            machine(66, 54),
            native(0),
            machine(66, 54),
            {"pooled": {"high_false_positive": rate(0, 4)}},
        )


def test_frozen_selection_uses_all_four_tie_breaks_and_falls_back():
    from vibechecker_eval.academic_addition import select_winner

    def case(worst, pooled, stress, anchor, reasons=None):
        return {
            "ordinary": {"worst_stratum_ece": worst, "pooled_ece": pooled},
            "books_news_stress": {"strata": {"pooled": {"brier": stress}}},
            "anchor": anchor,
            "admission_reasons": reasons or [],
        }

    eligible = case(0.2, 0.02, 0.1, 0.75)
    for lesser in (
        case(0.3, 0.01, 0.01, 0.5),
        case(0.2, 0.03, 0.01, 0.5),
        case(0.2, 0.02, 0.2, 0.5),
    ):
        assert select_winner({"a": eligible, "b": lesser}) == "a"
    assert select_winner({"a": eligible, "b": case(0.2, 0.02, 0.1, 0.5)}) == "b"
    assert select_winner({"a": case(0, 0, 0, 0.5, ["specificity"])}) == "incumbent"
