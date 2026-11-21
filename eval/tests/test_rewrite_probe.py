from dataclasses import replace

import joblib
import numpy as np
import pytest
from vibechecker_eval.rewrite_data import RewriteDocument, RewritePair
from vibechecker_eval.rewrite_probe import (
    Row,
    _cohorts,
    _qualifies,
    fit_candidates,
    paired_origin_membership,
)


def test_pair_origin_probe_is_portable_and_preserves_the_downward_ceiling(tmp_path):
    rng = np.random.default_rng(344)
    general, paired = [[], [], []], [[], [], []]
    for role, count in enumerate((38, 12, 5)):
        for i in range(count):
            group = f"{role}-{i}"
            for label in (0, 1):
                for attack in ("none", "paraphrase"):
                    vector = rng.normal(size=769)
                    vector[0] += 4 * (attack == "paraphrase")
                    vector[1] += 3 * label
                    row = Row(
                        f"pair-{group}-{attack}-{label}",
                        group,
                        label,
                        "news",
                        attack,
                        "fixture",
                        vector,
                    )
                    paired[role].append(row)
                vector = rng.normal(size=769)
                vector[1] += 4 * label
                general[role].append(
                    Row(
                        f"general-{group}-{label}", group, label, "essay", "none", "fixture", vector
                    )
                )
    models = fit_candidates(general, paired, 42)
    x = np.stack([r.vector for r in paired[2]])
    for name in ("mixture", "downward"):
        model = models[name]
        p = model.predict_proba(x)
        assert model.n_features_in_ == 769
        assert model.classes_.tolist() == [0, 1]
        np.testing.assert_allclose(p.sum(axis=1), 1)
        np.testing.assert_allclose(
            np.vstack([model.predict_proba(v[None, :]) for v in x]), p, atol=1e-6
        )
        path = tmp_path / (name + ".joblib")
        joblib.dump(model, path)
        np.testing.assert_array_equal(joblib.load(path).predict_proba(x), p)
        with pytest.raises(ValueError, match="769"):
            model.predict_proba(np.zeros((1, 768)))
    assert np.all(
        models["downward"].predict_proba(x)[:, 1] <= models["general"].predict_proba(x)[:, 1]
    )


def test_source_conflicts_revoke_both_groups_before_partitioning():
    zero = np.zeros(769)
    a = Row("shared", "a", 1, "books", "none", "example", zero)
    b = Row("shared", "b", 1, "books", "none", "example", zero)
    other = Row("other", "a", 1, "books", "paraphrase", "example", zero)
    retained = Row("kept", "c", 0, "news", "none", "human", zero)
    general, supplement, conflicts = _cohorts([a, retained], [b, other], 42)
    assert conflicts == {"a", "b"}
    assert [r.id for role in general for r in role] == ["kept"]
    assert not any(supplement)


def test_candidate_requires_paired_origin_benefit_and_protected_ordinary_writing():
    scores = {
        "origin_domain/books": {
            "scores": {"general": {"log_loss": 0.5}, "downward": {"log_loss": 0.2}}
        },
        "origin_domain/news": {
            "scores": {"general": {"log_loss": 0.5}, "downward": {"log_loss": 0.2}}
        },
        "origin": {"paired": {"downward": {"log_loss_delta_95": [-0.4, -0.01]}}},
        "human": {
            "scores": {
                "general": {"false_positives_at_half": 2},
                "downward": {"false_positives_at_half": 2},
            }
        },
        "clean_machine": {"paired": {"downward": {"error_rate_delta_95": [0, 0.008]}}},
    }
    assert _qualifies("downward", scores)
    scores["human"]["scores"]["downward"]["false_positives_at_half"] = 3
    assert not _qualifies("downward", scores)


def test_membership_binds_authenticated_head_document_ids_to_source_folds():
    pairs = []
    for i in range(30):
        docs = [
            RewriteDocument(f"doc-{i}-{j}", "pub", "parent", "", "generator", 400) for j in range(4)
        ]
        pairs.append(RewritePair(f"raid:source-{i}", "head", "news", *docs))
    roles = paired_origin_membership(pairs, 42)
    assert sum(v["groups"] for v in roles.values()) == len(pairs)
    assert all(v["documents"] == 4 * v["groups"] for v in roles.values())
    changed = replace(pairs[0], human=replace(pairs[0].human, id="changed"))
    revised = paired_origin_membership([changed, *pairs[1:]], 42)
    assert (
        sum(roles[r]["document_ids_sha256"] != revised[r]["document_ids_sha256"] for r in roles)
        == 1
    )
    assert all(roles[r]["group_ids_sha256"] == revised[r]["group_ids_sha256"] for r in roles)
    with pytest.raises(ValueError, match="head pairs"):
        paired_origin_membership([replace(pairs[0], role="stress")], 42)
