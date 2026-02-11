"""Board texture analysis for postflop decision making."""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter

from ..cards import rank_index, RANKS


@dataclass(frozen=True)
class BoardTexture:
    """Characterizes how dangerous/coordinated the community cards are."""

    is_monotone: bool        # all one suit (flush possible for anyone)
    is_two_tone: bool        # two suits dominate (flush draw likely)
    is_rainbow: bool         # 3+ suits (flush unlikely)
    is_paired: bool          # board has a pair (full house possible)
    is_double_paired: bool   # two pairs on board
    is_trip_board: bool      # three of a kind on board
    has_straight_draw: bool  # 3+ cards within 4 rank span
    is_connected: bool       # most cards within close ranks
    high_card_rank: int      # highest card rank on board (0-12)
    num_broadway: int        # number of T+ cards
    num_community: int       # how many community cards are out


def analyze_board(community: tuple[str, ...]) -> BoardTexture:
    """Analyze the texture of community cards."""
    if not community:
        return BoardTexture(
            is_monotone=False, is_two_tone=False, is_rainbow=True,
            is_paired=False, is_double_paired=False, is_trip_board=False,
            has_straight_draw=False, is_connected=False,
            high_card_rank=0, num_broadway=0, num_community=0,
        )

    suits = [c[1] for c in community]
    ranks = [rank_index(c) for c in community]
    suit_counts = Counter(suits)
    rank_counts = Counter(ranks)

    max_suit_count = max(suit_counts.values())
    is_monotone = max_suit_count >= 3 and len(community) <= 3 or max_suit_count >= 4
    is_two_tone = not is_monotone and max_suit_count >= 2
    is_rainbow = max_suit_count == 1

    pair_count = sum(1 for c in rank_counts.values() if c >= 2)
    trip_on_board = any(c >= 3 for c in rank_counts.values())

    # Straight draw detection: any window of 5 consecutive ranks
    # containing 3+ board cards
    sorted_ranks = sorted(set(ranks))
    has_straight_draw = False
    is_connected = False
    for i in range(len(sorted_ranks)):
        for j in range(i + 1, len(sorted_ranks)):
            if sorted_ranks[j] - sorted_ranks[i] <= 4:
                cards_in_window = sum(
                    1 for r in sorted_ranks[i:j + 1]
                    if sorted_ranks[i] <= r <= sorted_ranks[i] + 4
                )
                if cards_in_window >= 3:
                    has_straight_draw = True
                if cards_in_window >= 2 and sorted_ranks[j] - sorted_ranks[i] <= 2:
                    is_connected = True

    # Check ace-low straight draw (A-2-3-4-5 territory)
    if 12 in ranks and any(r <= 3 for r in ranks):
        low_ranks = [r for r in ranks if r <= 3] + [12]
        if len(low_ranks) >= 3:
            has_straight_draw = True

    high_card_rank = max(ranks) if ranks else 0
    num_broadway = sum(1 for r in ranks if r >= 8)  # T=8 and above

    return BoardTexture(
        is_monotone=is_monotone,
        is_two_tone=is_two_tone,
        is_rainbow=is_rainbow,
        is_paired=pair_count >= 1,
        is_double_paired=pair_count >= 2,
        is_trip_board=trip_on_board,
        has_straight_draw=has_straight_draw,
        is_connected=is_connected,
        high_card_rank=high_card_rank,
        num_broadway=num_broadway,
        num_community=len(community),
    )


def has_flush_draw(hole: tuple[str, str], community: tuple[str, ...]) -> bool:
    """Check if we have 4 cards of same suit (1 card from flush)."""
    if len(community) < 3:
        return False
    all_suits = [c[1] for c in (*hole, *community)]
    return max(Counter(all_suits).values()) == 4


def has_flush(hole: tuple[str, str], community: tuple[str, ...]) -> bool:
    """Check if we have 5+ cards of same suit."""
    if len(community) < 3:
        return False
    all_suits = [c[1] for c in (*hole, *community)]
    return max(Counter(all_suits).values()) >= 5


def has_open_ended_straight_draw(hole: tuple[str, str], community: tuple[str, ...]) -> bool:
    """Check if we have an open-ended straight draw (8 outs)."""
    if len(community) < 3:
        return False
    all_ranks = sorted(set(rank_index(c) for c in (*hole, *community)))

    # Look for 4 consecutive ranks
    for i in range(len(all_ranks) - 3):
        window = all_ranks[i:i + 4]
        if window[-1] - window[0] == 3:
            # Check that it's not capped (A-high or 2-low only count if open both ends)
            if window[0] > 0 and window[-1] < 12:
                return True
    return False


def has_overpair(hole: tuple[str, str], community: tuple[str, ...]) -> bool:
    """Check if our pocket pair is higher than all board cards."""
    if rank_index(hole[0]) != rank_index(hole[1]):
        return False  # not a pair
    if not community:
        return True
    our_rank = rank_index(hole[0])
    board_high = max(rank_index(c) for c in community)
    return our_rank > board_high


def has_top_pair(hole: tuple[str, str], community: tuple[str, ...]) -> bool:
    """Check if one of our hole cards pairs the highest board card."""
    if not community:
        return False
    board_high = max(rank_index(c) for c in community)
    return any(rank_index(h) == board_high for h in hole)


def top_pair_kicker_strength(hole: tuple[str, str], community: tuple[str, ...]) -> int:
    """If we have top pair, return the rank of our kicker (higher = better). -1 if no top pair."""
    if not community:
        return -1
    board_high = max(rank_index(c) for c in community)
    matching = [h for h in hole if rank_index(h) == board_high]
    if not matching:
        return -1
    non_matching = [h for h in hole if rank_index(h) != board_high]
    if non_matching:
        return rank_index(non_matching[0])
    return board_high  # pocket pair matching top card
