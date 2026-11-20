from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple, Protocol

import numpy as np


@dataclass(frozen=True)
class TokenStats:
    """Each entry describes a known next token, starting at ids[1]."""

    logp: np.ndarray
    rank: np.ndarray
    entropy: np.ndarray


class LMBackend(Protocol):
    name: str

    def token_stats(self, ids: Sequence[int]) -> TokenStats: ...


class PairStats(NamedTuple):
    # First four vectors describe the same observed next tokens. The Binoculars
    # denominator includes the final prediction and excludes pad-ID contexts.
    logp_a: np.ndarray
    cross: np.ndarray
    cross_sq: np.ndarray
    logp_b: np.ndarray
    binoculars_cross: np.ndarray

    @classmethod
    def concatenate(cls, parts):
        return cls(*(np.concatenate(column) for column in zip(*parts, strict=True)))


class PairBackend(Protocol):
    name: str

    def caches(self): ...

    def pair_stats(
        self, ids: Sequence[int], start: int, stop: int, caches, pad_id: int | None
    ) -> PairStats: ...
