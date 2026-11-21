import json
import sqlite3

import pytest
from vibechecker_eval import rewrite_data
from vibechecker_eval.loaders import fingerprint


def raw_group(role):
    return next(g for i in range(200) if rewrite_data._role(g := f"raid:test-{i}") == role)


def document(text, publisher, parent, generator):
    text = (text + " ") * 65
    return rewrite_data.RewriteDocument(
        fingerprint(text), publisher, parent, text, generator, len(text.split())
    )


def pair(group=None, role="head"):
    group = group or raw_group("stack" if role == "stress" else role)
    hid = group.removeprefix("raid:")
    return rewrite_data.RewritePair(
        group,
        role,
        "books",
        document("Students worked together on the paper.", "rewritten-human", hid, "human"),
        document(
            "Children discussed their books in class.", "rewritten-machine", "clean-ai", "gpt2"
        ),
        document("The group wrote its assignment together.", hid, hid, "human"),
        document("Students talked about a reading assignment.", "clean-ai", "clean-ai", "gpt2"),
    )


def test_load_checks_research_scope_and_exact_bytes(tmp_path, monkeypatch):
    p = pair()
    rows = [p]
    expected = {"selection_sha256": rewrite_data._payload_digest(rows)}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(expected))
    monkeypatch.setattr(rewrite_data, "MANIFEST", manifest)
    db = tmp_path / "cohort.sqlite"
    rewrite_data._write(db, rows, expected)
    assert rewrite_data.load_rewrite_pairs(db, role="head") == rows
    assert rewrite_data.load_rewrite_pairs(db, role="stress") == []
    with pytest.raises(ValueError, match="research-only"):
        rewrite_data.load_rewrite_pairs(db, role="head", commercial_only=True)
    with sqlite3.connect(db) as conn:
        raw = json.loads(conn.execute("SELECT payload FROM pairs").fetchone()[0])
        raw["human"]["text"] = raw["human"]["text"].upper()
        conn.execute("UPDATE pairs SET payload=?", (json.dumps(raw),))
    with pytest.raises(ValueError, match="pinned projection"):
        rewrite_data.load_rewrite_pairs(db, role="head")


def test_rejects_broken_parent_and_wrong_fold():
    from dataclasses import replace

    p = pair()
    with pytest.raises(ValueError, match="parent identity"):
        rewrite_data._check_pairs([replace(p, human=replace(p.human, parent_id="wrong"))])
    with pytest.raises(ValueError, match="source group"):
        rewrite_data._check_pairs([replace(p, role="stress")])


@pytest.mark.parametrize(
    "blocked_by", ["other_source", "label_conflict", "prospective", "previous_fit"]
)
def test_training_or_reserved_group_cannot_reach_stress(blocked_by):
    p = pair(role="stress")
    guard = rewrite_data._Guard()
    for kind in rewrite_data.KINDS:
        d = getattr(p, kind)
        guard.add(d.id, p.source_group, "stack", int(d.generator != "human"))
    prior, members = set(), []
    if blocked_by == "other_source":
        guard.add(p.machine.id, "raid:other", "stack", 1)
    elif blocked_by == "label_conflict":
        guard.add(p.machine.id, p.source_group, "stack", 0)
    elif blocked_by == "prospective":
        members.append([p.clean_human.id, fingerprint("another published group")])
    else:
        prior.add(p.source_group)
    wanted = {(p.domain, p.source_group): {True: [p.human], False: [p.machine]}}
    parents = {
        d.publisher_id: (p.source_group, p.domain, d) for d in (p.clean_human, p.clean_machine)
    }
    selected, audit = rewrite_data._choose(
        wanted, parents, guard, {}, {"members": members}, prior, set(), set()
    )
    assert not any(r.role == "stress" for r in selected)
    assert audit["stress_prior_fit_component_overlap"] == 0
    if blocked_by != "previous_fit":
        assert not selected
