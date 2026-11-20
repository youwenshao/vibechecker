from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

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
