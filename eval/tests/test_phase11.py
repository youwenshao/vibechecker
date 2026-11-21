from dataclasses import replace

import pytest
from vibechecker_eval.metrics import Observation, gates
from vibechecker_eval.phase11 import BASELINE, combine
from vibechecker_eval.subgroup_policy import fit, high_cutoff, keys, scorecard


def essay(i=0, **fields):
    return replace(
        Observation(
            str(i), 0, 0.10, "asap", "calibration", "essay", "unknown", "human", "none", 599, None
        ),
        **fields,
    )


def test_cutoffs_keep_ties_and_never_use_origin_labels():
    calibration = [essay(i, score=0.8 if i < 2 else 0) for i in range(50)]
    policy = fit(calibration, 24)
    assert high_cutoff(essay(), policy) == 81
    a = essay(dataset="liang/college-human", split="test")
    b = replace(a, dataset="liang/college-ai", label=1, writer="ESL", generator="gpt-3")
    assert keys(a) == keys(b) and high_cutoff(a, policy) == high_cutoff(b, policy) == 81
    assert keys(essay(words=600)) != keys(essay(words=599))
    assert high_cutoff(essay(dataset="unseen", words=90), policy) == 81
    assert high_cutoff(essay(), fit(calibration[:49], 24)) == 24
    with pytest.raises(ValueError, match="Only calibration"):
        fit([*calibration, a], 24)


def test_band_changes_leave_ece_fixed_and_report_machine_losses():
    data = [essay(score=0.4), essay(1, score=0.6, label=1, generator="machine")]
    base = scorecard(data, BASELINE, 0.01)
    policy = dict(BASELINE, cutoffs={"source-length/asap/300-599": {"high": 61}})
    card = scorecard(data, policy, 0.01)
    for key in base:
        assert card[key]["ece"] == base[key]["ece"]
    for key in ["pooled", "source-length/asap/300-599"]:
        assert card[key]["fpr_high"]["count"] == card[key]["recall_high"]["count"] == 0
        assert base[key]["fpr_high"]["count"] == base[key]["recall_high"]["count"] == 1


def test_guarded_cutoff_requires_support_and_respects_rounded_ties():
    rows = [essay(i, score=0.82 if i < 2 else 0) for i in range(149)]
    assert high_cutoff(essay(), fit(rows[:-1], 24, guarded=True)) == 24
    assert high_cutoff(essay(), fit(rows, 24, guarded=True)) == 83
    with pytest.raises(ValueError, match="unattainable"):
        fit([replace(row, score=1) for row in rows], 24, guarded=True)


def test_probability_adjustment_uses_both_classes_and_supported_cells():
    data = [essay(i, label=i % 2, score=0.8 if i % 2 else 0.2) for i in range(1000)]
    assert fit(data[:-1], 24, adjust=True)["powers"] == {}
    policy = fit(data, 24, adjust=True)
    assert policy["powers"]["pooled"] == 2
    assert (
        scorecard(data, policy, 0.01)["pooled"]["ece"]
        < scorecard(data, BASELINE, 0.01)["pooled"]["ece"]
    )


def test_audit_coverage_and_combination_check_both_sources_and_documents():
    a = essay()
    b = essay(1, dataset="liang/college-human")
    card = scorecard([a], BASELINE, 0.01)
    check = gates(card, quick=False, deep=True, require_college=True)["checks"][
        "human_essay_high_fpr"
    ]
    assert check["status"] == "incomplete" and check["value"] == 0
    with pytest.raises(ValueError, match="failing admissions"):
        combine([a], [], {})
    with pytest.raises(ValueError, match="Overlapping"):
        combine([a], [b], {"0": "same", "1": "same"})
    with pytest.raises(ValueError, match="Overlapping"):
        combine([b], [b], {"1": "b"})
    assert combine([a], [b], {"0": "a", "1": "b"}) == [a, b]
