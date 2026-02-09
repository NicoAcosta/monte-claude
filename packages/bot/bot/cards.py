"""Card notation conversion between Monteclaude and phevaluator."""

from __future__ import annotations

import random

RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")
SUITS = ("c", "d", "h", "s")

# phevaluator accepts string cards like "Ah", "Tc" directly —
# same notation as Monteclaude. No conversion needed.
# We only need utilities for Monte Carlo simulation (dealing random cards).

ALL_CARDS: tuple[str, ...] = tuple(f"{r}{s}" for r in RANKS for s in SUITS)


def rank_index(card: str) -> int:
    """Return 0-12 rank index (2=0, A=12)."""
    return RANKS.index(card[0])


def is_suited(a: str, b: str) -> bool:
    return a[1] == b[1]


def is_pair(a: str, b: str) -> bool:
    return a[0] == b[0]


def gap(a: str, b: str) -> int:
    """Rank gap between two cards (0 = connected)."""
    return abs(rank_index(a) - rank_index(b)) - 1


class SimDeck:
    """Deck for Monte Carlo simulation — deals random cards excluding known cards."""

    __slots__ = ("_available", "_rng")

    def __init__(self, exclude: tuple[str, ...], rng: random.Random) -> None:
        self._available = [c for c in ALL_CARDS if c not in exclude]
        rng.shuffle(self._available)
        self._rng = rng

    def deal(self, n: int) -> list[str]:
        """Deal n cards from the shuffled deck."""
        if n > len(self._available):
            raise RuntimeError(f"Need {n} cards but only {len(self._available)} left")
        dealt = self._available[:n]
        self._available = self._available[n:]
        return dealt
