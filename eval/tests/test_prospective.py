from dataclasses import replace
from types import SimpleNamespace

import pytest
from vibechecker_eval.deep_cohort import fold
from vibechecker_eval.deep_runner import run_deep
from vibechecker_eval.loaders import Example, fingerprint
from vibechecker_eval.prospective import digest, manifest, plan_digest, publish, reserve, resolve
from vibechecker_eval.runner import sample


def words(text):
    return 2 if text.startswith("Short") else 400


def envelope(rows, datasets):
    historical = {
        fingerprint(r.text): r.source_group
        for r, _ in sample(rows, 72, 42, words, length_range=(300, 2500))[0]
        if r.split == "test" and fold(r, "bakeoff") == 1
    }
    return historical, {
        "input_manifest": manifest(datasets),
        "after": {
            "final_envelope": {
                "documents": len(historical),
                "source_groups": len(set(historical.values())),
                "document_id_sha256": digest(historical),
            }
        },
    }


def test_blind_group_reservation_replays_and_excludes_linked_variants():
    datasets = [SimpleNamespace(id="raid", version="pin", artifacts=[])]
    rows = [
        Example(
            f"Document {i}",
            i % 2,
            "raid",
            "test",
            "other",
            generator=f"g{i % 4}",
            source_group=f"source-{i}",
        )
        for i in range(1500)
    ]
    history, _ = envelope(rows, datasets)
    safe = [r for r in rows if r.source_group not in history.values() and fold(r, "bakeoff") == 1]
    a, b, c, d = safe[:4]
    # Short human originals and unrelated generated variants can connect groups
    # across multiple steps, even though none enters the old length reservoir.
    for source, split, text, label in (
        ("train", "train", "Short shared human", 0),
        (a.source_group, "test", "Short shared human", 0),
        (a.source_group, "test", "Short repeated generator", 1),
        (b.source_group, "test", "Short repeated generator", 1),
        (next(iter(history.values())), "test", "Short historical sibling", 1),
        (c.source_group, "test", "Short historical sibling", 1),
        (d.source_group, "calibration", "Short calibration doc", 0),
    ):
        rows.append(Example(text, label, "raid", split, "other", source_group=source))
    history, audit = envelope(rows, datasets)
    plan = reserve(lambda: iter(rows), words, audit, datasets, target=3000)
    expected_sha = plan_digest(plan)
    assert plan == reserve(lambda: iter(rows), words, audit, datasets, target=3000)
    assert plan["selection"]["source_components"] == len(plan["members"]) > 400
    assert all(v == 0 for k, v in plan["isolation"].items() if k.endswith("_overlap"))
    selected = dict(plan["members"])
    assert set(selected).isdisjoint(history)
    assert set(selected.values()).isdisjoint(
        fingerprint(g)
        for g in [*history.values(), a.source_group, b.source_group, c.source_group, d.source_group]
    )
    eligible = resolve(plan, expected_sha, datasets, iter(rows), words)
    assert [fingerprint(r.text) for r, _ in eligible] == sorted(selected)
    assert all(len(key) == 64 and len(group) == 64 for key, group in plan["members"])
    invalid = {**plan, "members": plan["members"][:-1]}
    with pytest.raises(ValueError, match="digest"):
        resolve(invalid, expected_sha, datasets, iter(rows), words)
    with pytest.raises(ValueError, match="Missing"):
        resolve(plan, expected_sha, datasets, iter(()), words)
    with pytest.raises(ValueError, match="different source or split"):
        resolve(plan, expected_sha, datasets, [replace(eligible[0][0], split="train")], words)
    with pytest.raises(ValueError, match="historical candidate envelope"):
        reserve(
            lambda: iter(rows),
            words,
            {
                **audit,
                "after": {"final_envelope": {**audit["after"]["final_envelope"], "documents": 0}},
            },
            datasets,
        )


def test_prospective_requires_frozen_model_before_any_extraction(tmp_path):
    path = tmp_path / "candidate.joblib"
    path.write_bytes(b"frozen candidate")
    args = SimpleNamespace(
        cohort="prospective",
        audit_plan=tmp_path / "plan.json",
        model_in=path,
        audit_model_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="SHA-pinned frozen model"):
        run_deep(args, [])


def test_published_reservation_is_idempotent_and_immutable(tmp_path):
    path = tmp_path / "frozen" / "manifest.json"
    publish({"members": [1, 2]}, path)
    original = path.read_bytes()
    publish({"members": [1, 2]}, path)
    with pytest.raises(ValueError, match="different plan"):
        publish({"members": [2]}, path)
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]
