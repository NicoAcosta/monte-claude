from __future__ import annotations

import random
from dataclasses import dataclass

SUITS = ("s", "h", "d", "c")
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")
RANK_VALUES: dict[str, int] = {r: i for i, r in enumerate(RANKS)}

SUIT_SYMBOLS: dict[str, str] = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}


@dataclass(frozen=True, slots=True)
class Card:
    rank: str
    suit: str

    def __post_init__(self) -> None:
        if self.rank not in RANK_VALUES:
            raise ValueError(f"Invalid rank: {self.rank}")
        if self.suit not in SUIT_SYMBOLS:
            raise ValueError(f"Invalid suit: {self.suit}")

    @property
    def rank_value(self) -> int:
        return RANK_VALUES[self.rank]

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def display(self) -> str:
        return f"{self.rank}{SUIT_SYMBOLS[self.suit]}"

    @classmethod
    def from_str(cls, s: str) -> Card:
        if len(s) != 2:
            raise ValueError(f"Card string must be 2 chars, got: {s!r}")
        return cls(rank=s[0], suit=s[1])


def full_deck() -> list[Card]:
    return [Card(rank=r, suit=s) for s in SUITS for r in RANKS]


class Deck:
    def __init__(self, seed: int | None = None) -> None:
        self._cards = full_deck()
        self._rng = random.Random(seed)
        self._rng.shuffle(self._cards)
        self._index = 0

    def deal(self, count: int = 1) -> list[Card]:
        if self._index + count > len(self._cards):
            raise RuntimeError("Not enough cards in deck")
        cards = self._cards[self._index : self._index + count]
        self._index += count
        return cards

    @property
    def remaining(self) -> int:
        return len(self._cards) - self._index
