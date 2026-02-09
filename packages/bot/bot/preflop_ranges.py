"""GTO-ish preflop opening/calling ranges by position."""

from __future__ import annotations

from enum import Enum

from .cards import gap, is_pair, is_suited, rank_index


class Position(Enum):
    EARLY = "early"
    MIDDLE = "middle"
    LATE = "late"
    BLIND = "blind"


class HandTier(Enum):
    PREMIUM = "premium"      # AA, KK, QQ, AKs
    STRONG = "strong"        # JJ, TT, AK, AQs, KQs
    PLAYABLE = "playable"    # 99-77, AJs-ATs, KJs, QJs, suited connectors
    MARGINAL = "marginal"    # 66-22, suited aces, suited connectors, broadways
    TRASH = "trash"


class PreflopAction(Enum):
    RAISE = "raise"
    CALL = "call"
    FOLD = "fold"


def classify_hand(a: str, b: str) -> HandTier:
    """Classify a 2-card starting hand into a tier."""
    hi = max(rank_index(a), rank_index(b))  # 0=2, 12=A
    lo = min(rank_index(a), rank_index(b))
    suited = is_suited(a, b)
    pair = is_pair(a, b)
    g = gap(a, b)

    # Premium: AA, KK, QQ, AKs
    if pair and hi >= 10:  # QQ+
        return HandTier.PREMIUM
    if hi == 12 and lo == 11 and suited:  # AKs
        return HandTier.PREMIUM

    # Strong: JJ, TT, AK, AQs, KQs
    if pair and hi >= 8:  # TT, JJ
        return HandTier.STRONG
    if hi == 12 and lo == 11:  # AKo
        return HandTier.STRONG
    if hi == 12 and lo == 10 and suited:  # AQs
        return HandTier.STRONG
    if hi == 11 and lo == 10 and suited:  # KQs
        return HandTier.STRONG

    # Playable: 99-77, AJs-ATs, AQ, KJs, QJs, suited connectors 89s+
    if pair and hi >= 5:  # 77-99
        return HandTier.PLAYABLE
    if hi == 12 and lo >= 8 and suited:  # ATs+
        return HandTier.PLAYABLE
    if hi == 12 and lo == 10:  # AQo
        return HandTier.PLAYABLE
    if hi == 11 and lo >= 9 and suited:  # KTs+
        return HandTier.PLAYABLE
    if hi == 10 and lo == 9 and suited:  # QJs
        return HandTier.PLAYABLE
    if suited and g == 0 and lo >= 6:  # 89s, 9Ts+
        return HandTier.PLAYABLE

    # Marginal: 66-22, suited aces, more suited connectors, broadway combos
    if pair:  # 22-66
        return HandTier.MARGINAL
    if hi == 12 and suited:  # Axs
        return HandTier.MARGINAL
    if suited and g == 0 and lo >= 3:  # 56s-78s
        return HandTier.MARGINAL
    if suited and g == 1 and lo >= 5:  # 68s, 79s, etc.
        return HandTier.MARGINAL
    if hi >= 9 and lo >= 9:  # KQ, KJ, QJ, KT, QT, JT offsuit
        return HandTier.MARGINAL

    return HandTier.TRASH


def determine_position(
    our_player_id: int,
    dealer_id: int,
    player_ids: tuple[int, ...],
) -> Position:
    """Determine our position relative to the dealer.

    player_ids should be active (non-resigned) player IDs in seat order.
    """
    n = len(player_ids)
    if n <= 2:
        # Heads-up: dealer is small blind (acts first preflop, last postflop)
        if our_player_id == dealer_id:
            return Position.LATE
        return Position.BLIND

    dealer_idx = player_ids.index(dealer_id)
    our_idx = player_ids.index(our_player_id)

    # Distance from dealer (1 = SB, 2 = BB, 3 = UTG, ...)
    distance = (our_idx - dealer_idx) % n

    if distance <= 2:  # SB or BB
        return Position.BLIND
    if n <= 4:
        # 3-4 players: after blinds everyone is late
        return Position.LATE

    # 5+ players: split remaining seats into early/middle/late
    remaining = n - 2  # Exclude blinds
    pos_in_order = distance - 2  # 1-based position after blinds

    third = remaining / 3
    if pos_in_order <= third:
        return Position.EARLY
    if pos_in_order <= 2 * third:
        return Position.MIDDLE
    return Position.LATE


# Position → (tiers that raise, tiers that call)
_RANGES: dict[Position, tuple[set[HandTier], set[HandTier]]] = {
    Position.EARLY: (
        {HandTier.PREMIUM, HandTier.STRONG},
        {HandTier.PLAYABLE},
    ),
    Position.MIDDLE: (
        {HandTier.PREMIUM, HandTier.STRONG, HandTier.PLAYABLE},
        {HandTier.MARGINAL},
    ),
    Position.LATE: (
        {HandTier.PREMIUM, HandTier.STRONG, HandTier.PLAYABLE},
        {HandTier.MARGINAL},
    ),
    Position.BLIND: (
        {HandTier.PREMIUM, HandTier.STRONG},
        {HandTier.PLAYABLE, HandTier.MARGINAL},
    ),
}


def preflop_action(
    hand_tier: HandTier,
    position: Position,
    facing_raise: bool,
) -> PreflopAction:
    """Decide preflop action based on hand tier and position.

    facing_raise: True if we need to call a raise (amount_to_call > big blind).
    """
    raise_tiers, call_tiers = _RANGES[position]

    if facing_raise:
        # Tighten up vs a raise: only re-raise premiums, call strongs
        if hand_tier == HandTier.PREMIUM:
            return PreflopAction.RAISE
        if hand_tier in raise_tiers:
            return PreflopAction.CALL
        if hand_tier in call_tiers and position in (Position.LATE, Position.BLIND):
            return PreflopAction.CALL
        return PreflopAction.FOLD

    # No raise to face (we can limp/open)
    if hand_tier in raise_tiers:
        return PreflopAction.RAISE
    if hand_tier in call_tiers:
        return PreflopAction.CALL
    return PreflopAction.FOLD
