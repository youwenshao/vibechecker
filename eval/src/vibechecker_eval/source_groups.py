"""Quarantine publisher source groups that share a normalized human passage."""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass

from .loaders import Example, fingerprint


def source_key(item: Example, *, document_id: str | None = None) -> str:
    """The source identity used before hashing or partitioning a selection."""
    return item.source_group or document_id or fingerprint(item.text)


@dataclass(frozen=True)
class HumanSourceAliases:
    groups: frozenset[str]
    passage_count: int
    sha256: str

    def summary(self):
        return {
            "scheme": "normalized-human-source-aliases-v1",
            "group_count": len(self.groups),
            "passage_count": self.passage_count,
            "sha256": self.sha256,
        }


def human_source_aliases(stream: Iterable[Example]) -> HumanSourceAliases:
    """Scan all splits and lengths before selecting fit rows.

    A short human original can identify two publisher groups whose generated
    derivatives both pass the length gate. Only human originals establish an
    alias: generators can repeat stock passages in response to unrelated prompts.
    """
    first: dict[str, str] = {}
    conflicts: dict[str, set[str]] = {}
    for item in stream:
        if item.label != 0:
            continue
        passage = fingerprint(item.text)
        group = source_key(item, document_id=passage)
        previous = first.setdefault(passage, group)
        if previous != group:
            conflicts.setdefault(passage, {previous}).add(group)

    groups = set()
    digest = hashlib.sha256()
    for passage, aliases in sorted(conflicts.items()):
        groups.update(aliases)
        # Bind the passage-to-group mapping as well as the exclusion set.
        record = json.dumps([passage, sorted(aliases)], separators=(",", ":"))
        digest.update((record + "\n").encode("utf8"))
    return HumanSourceAliases(frozenset(groups), len(conflicts), digest.hexdigest())
