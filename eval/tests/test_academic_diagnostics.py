import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest
from vibechecker_eval.academic_development import commitment, retained_groups, round_robin
from vibechecker_eval.academic_features import verify_cache
from vibechecker_eval.rewrite_diagnostics import similarities, stages


def test_registration_uses_existing_group_commitment():
    kept = {"a", "c"}
    report = {"rewritten_prompt_groups": 2, "rewritten_group_sha256": commitment(kept)}
    assert retained_groups({"a", "b", "c"}, report) == kept
    chosen = round_robin({"one": [("a", "doc-a"), ("b", "doc-b")], "two": [("c", "doc-c")]}, kept)
    assert chosen == {"a": ("one", "doc-a"), "c": ("two", "doc-c")}
    with pytest.raises(ValueError, match="commitment"):
        retained_groups({"d", "e"}, report)


def test_numeric_resume_verifies_metadata_shape_and_completion():
    row = {
        "id": "first",
        "group": "source",
        "kind": "rewrite",
        "domain": "abstracts",
        "generator": "one",
    }
    with sqlite3.connect(":memory:") as db:
        db.execute(
            "CREATE TABLE documents(rowno,id,source,kind,domain,generator,words,features,encoder)"
        )
        db.execute(
            "INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?)",
            (0, *row.values(), 401, np.zeros(13, "<f8").tobytes(), np.zeros(769, "<f4").tobytes()),
        )
        have, digest, kinds = verify_cache(db, [row], complete=True)
        assert have == {"first": 0} and len(digest) == 64 and kinds == {"rewrite": 1}
        with pytest.raises(ValueError, match="Incomplete"):
            verify_cache(db, [row, {"id": "second"}], complete=True)
        with pytest.raises(ValueError, match="membership"):
            verify_cache(db, [{**row, "kind": "same_prompt_clean"}])
        db.execute("UPDATE documents SET features=?", (np.zeros(12, "<f8").tobytes(),))
        with pytest.raises(ValueError, match="numeric"):
            verify_cache(db, [row])


def test_integrity_measures_token_order_and_shared_shingles():
    native = "one two three four five six seven"
    assert similarities(native, "ONE   two three four five six seven") == (1.0, 1.0)
    ratio, jaccard = similarities(native, "seven six five four three two one")
    assert ratio < 0.5 and jaccard == 0


def test_scoring_stages_distinguish_anchored_isotonic_and_rounding():
    class Probe:
        def predict_proba(self, x):
            return np.column_stack((1 - x[:, 0], x[:, 0]))

    class Classifier:
        estimator = SimpleNamespace(decision_function=lambda x: np.zeros(len(x)))

        def predict_proba(self, x):
            return np.column_stack((1 - x[:, -1], x[:, -1]))

    stacker = SimpleNamespace(
        classifier=Classifier(),
        high_threshold=34,
        calibrators={"pooled": SimpleNamespace(point=lambda x: 0.996 if x > 0.5 else 0.004)},
    )
    rows = [
        SimpleNamespace(
            features=np.zeros(13), encoder=np.array([val]), words=400, label=1, group=str(i)
        )
        for i, val in enumerate((0.055, 0.97))
    ]
    metrics = stages(stacker, Probe(), rows)
    assert metrics["anchored_before_isotonic"]["min"] == 0.055
    assert metrics["isotonic"]["min"] == 0.004 and metrics["isotonic"]["max"] == 0.996
    assert metrics["displayed"]["exact_zero"] == metrics["displayed"]["exact_one"] == 1
    assert metrics["high_band"] == {"index_threshold": 34, "hits": 1}
