from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poker.deck import Card

HAND_RANKS = {
    "high_card": 0,
    "one_pair": 1,
    "two_pair": 2,
    "three_of_a_kind": 3,
    "straight": 4,
    "flush": 5,
    "full_house": 6,
    "four_of_a_kind": 7,
    "straight_flush": 8,
    "royal_flush": 9,
}


class HandRank:
    __slots__ = ("rank", "name", "kickers")

    def __init__(self, rank: int, name: str, kickers: tuple[int, ...]) -> None:
        self.rank = rank
        self.name = name
        self.kickers = kickers

    def __lt__(self, other: HandRank) -> bool:
        if self.rank != other.rank:
            return self.rank < other.rank
        return self.kickers < other.kickers

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HandRank):
            return NotImplemented
        return self.rank == other.rank and self.kickers == other.kickers

    def __le__(self, other: HandRank) -> bool:
        return self == other or self < other

    def __gt__(self, other: HandRank) -> bool:
        return not self <= other

    def __ge__(self, other: HandRank) -> bool:
        return not self < other

    def __repr__(self) -> str:
        return f"HandRank({self.name}, kickers={self.kickers})"


def evaluate_five(cards: tuple[Card, ...]) -> HandRank:
    assert len(cards) == 5

    ranks = sorted((c.rank_value for c in cards), reverse=True)
    suits = [c.suit for c in cards]

    is_flush = len(set(suits)) == 1

    # Check straight
    is_straight = False
    straight_high = 0
    if ranks[0] - ranks[4] == 4 and len(set(ranks)) == 5:
        is_straight = True
        straight_high = ranks[0]
    # Ace-low straight (A-2-3-4-5): ranks sorted are [12, 3, 2, 1, 0]
    elif set(ranks) == {12, 3, 2, 1, 0}:
        is_straight = True
        straight_high = 3  # 5-high straight

    if is_flush and is_straight:
        if straight_high == 12:  # Ace-high
            return HandRank(HAND_RANKS["royal_flush"], "royal_flush", (straight_high,))
        return HandRank(HAND_RANKS["straight_flush"], "straight_flush", (straight_high,))

    # Count rank frequencies
    from collections import Counter

    counts = Counter(ranks)
    freq = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)

    if freq[0][1] == 4:
        quad_rank = freq[0][0]
        kicker = freq[1][0]
        return HandRank(HAND_RANKS["four_of_a_kind"], "four_of_a_kind", (quad_rank, kicker))

    if freq[0][1] == 3 and freq[1][1] == 2:
        trip_rank = freq[0][0]
        pair_rank = freq[1][0]
        return HandRank(HAND_RANKS["full_house"], "full_house", (trip_rank, pair_rank))

    if is_flush:
        return HandRank(HAND_RANKS["flush"], "flush", tuple(ranks))

    if is_straight:
        return HandRank(HAND_RANKS["straight"], "straight", (straight_high,))

    if freq[0][1] == 3:
        trip_rank = freq[0][0]
        kickers = sorted((r for r, c in freq if c == 1), reverse=True)
        return HandRank(
            HAND_RANKS["three_of_a_kind"],
            "three_of_a_kind",
            (trip_rank, *kickers),
        )

    if freq[0][1] == 2 and freq[1][1] == 2:
        high_pair = max(freq[0][0], freq[1][0])
        low_pair = min(freq[0][0], freq[1][0])
        kicker = freq[2][0]
        return HandRank(
            HAND_RANKS["two_pair"], "two_pair", (high_pair, low_pair, kicker)
        )

    if freq[0][1] == 2:
        pair_rank = freq[0][0]
        kickers = sorted((r for r, c in freq if c == 1), reverse=True)
        return HandRank(HAND_RANKS["one_pair"], "one_pair", (pair_rank, *kickers))

    return HandRank(HAND_RANKS["high_card"], "high_card", tuple(ranks))


def best_hand(cards: list[Card]) -> HandRank:
    """Find best 5-card hand from 5, 6, or 7 cards."""
    if len(cards) < 5:
        raise ValueError(f"Need at least 5 cards, got {len(cards)}")
    if len(cards) == 5:
        return evaluate_five(tuple(cards))
    best = None
    for combo in combinations(cards, 5):
        rank = evaluate_five(combo)
        if best is None or rank > best:
            best = rank
    assert best is not None
    return best
