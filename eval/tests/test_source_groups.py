import hashlib

from vibechecker_eval.loaders import Example, fingerprint
from vibechecker_eval.source_groups import human_source_aliases, source_key


def record(text, group, *, label=0, split="train", dataset="raid"):
    return Example(text, label, dataset, split, "other", source_group=group)


def test_blocks_all_groups_linked_by_any_human_original_across_splits_and_lengths():
    standalone = record("Human ORIGINAL.", None, split="test", dataset="liang/toefl")
    stream = [
        standalone,
        record("  human\noriginal. ", "raid:b"),
        record("Another short original.", "raid:b", split="calibration"),
        record("ANOTHER SHORT ORIGINAL.", "raid:c"),
        record("Another short original.", "raid:c"),
        record("Original without aliases.", "raid:keep"),
    ]
    audit = human_source_aliases(iter(stream))
    assert audit.groups == {fingerprint(standalone.text), "raid:b", "raid:c"}
    assert audit.passage_count == 2
    assert source_key(record("Longer derived passage.", "raid:c", label=1)) in audit.groups
    assert source_key(standalone, document_id=fingerprint(standalone.text)) in audit.groups
    assert audit.summary()["group_count"] == 3
    assert audit.summary() == human_source_aliases(reversed(stream)).summary()


def test_repeated_generated_passages_and_same_group_repetitions_do_not_create_aliases():
    stream = [
        record("A common answer.", "first"),
        record("A common answer.", "first", split="test"),
        record("A common answer.", "second", label=1),
        record("A common answer.", "third", label=1),
    ]
    audit = human_source_aliases(stream)
    assert not audit.groups
    assert audit.passage_count == 0
    assert audit.sha256 == hashlib.sha256(b"").hexdigest()


def test_digest_changes_if_the_same_groups_are_linked_by_a_different_passage():
    def audit(text):
        return human_source_aliases([record(text, "a"), record(text, "b")])

    assert audit("One.").groups == audit("Two.").groups
    assert audit("One.").sha256 != audit("Two.").sha256
