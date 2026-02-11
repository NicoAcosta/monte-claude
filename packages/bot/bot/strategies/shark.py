"""Shark strategy: GTO-inspired preflop + opponent-adaptive postflop.

Key improvements over the base equity bot:
- Opponent modeling adjusts aggression vs passive/aggressive players
- Board texture analysis modifies equity thresholds
- Position-aware bet sizing
- Semi-bluff detection (flush/straight draws)
- Stack-depth-aware tournament adjustments
- Variable bet sizing based on hand strength and board
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..equity import estimate_equity
from ..preflop_ranges import (
    HandTier,
    Position,
    PreflopAction,
    classify_hand,
    determine_position,
    preflop_action,
)
from .board import (
    BoardTexture,
    analyze_board,
    has_flush,
    has_flush_draw,
    has_open_ended_straight_draw,
    has_overpair,
    has_top_pair,
    top_pair_kicker_strength,
)
from .opponent import OpponentProfile, OpponentTracker

log = logging.getLogger(__name__)

BIG_BLIND = 20
STARTING_CHIPS = 1000

# Global tracker persists across calls within one game session
_tracker = OpponentTracker()


@dataclass(frozen=True)
class Decision:
    action: str
    amount: int | None = None
    comment: str | None = None


def decide(state: dict[str, Any]) -> Decision:
    """Main entry point: state dict → Decision."""
    _tracker.update(state)

    phase = state["phase"]
    hole = tuple(state["your_cards"])
    community = tuple(state["community_cards"])
    pot = state["pot"]
    amount_to_call = state["amount_to_call"]
    min_raise = state["min_raise"]
    our_chips = state["your_chips"]

    if phase == "preflop":
        return _preflop(state, hole, amount_to_call, min_raise, our_chips)
    return _postflop(state, hole, community, pot, amount_to_call, min_raise, our_chips)


def reset_tracker() -> None:
    """Reset the global opponent tracker (for new games)."""
    global _tracker
    _tracker = OpponentTracker()


# ── Preflop ──────────────────────────────────────────


def _preflop(
    state: dict[str, Any],
    hole: tuple[str, ...],
    amount_to_call: int,
    min_raise: int,
    our_chips: int,
) -> Decision:
    """Preflop with position-aware sizing and opponent adjustment."""
    tier = classify_hand(hole[0], hole[1])
    position = _get_position(state)
    facing_raise = amount_to_call > BIG_BLIND
    opp_profiles = _get_opponent_profiles(state)

    # Adjust based on opponent tendencies
    action = _adjusted_preflop_action(tier, position, facing_raise, opp_profiles)
    tag = f"{tier.value}/{position.value}"

    if action == PreflopAction.FOLD:
        if amount_to_call == 0:
            return Decision("check", comment=f"[pre] {tag} check")
        return Decision("fold", comment=f"[pre] {tag} fold")

    if action == PreflopAction.CALL:
        if amount_to_call == 0:
            # With playable+ hands in position, sometimes raise to isolate
            if tier in (HandTier.PLAYABLE, HandTier.STRONG) and position == Position.LATE:
                raise_to = max(min_raise, BIG_BLIND * 3)
                if raise_to < our_chips:
                    return Decision("bet", amount=raise_to, comment=f"[pre] {tag} isolate")
            return Decision("check", comment=f"[pre] {tag} check")
        if amount_to_call >= our_chips:
            if tier in (HandTier.PREMIUM, HandTier.STRONG):
                return Decision("all_in", comment=f"[pre] {tag} all-in call")
            return Decision("fold", comment=f"[pre] {tag} too expensive")
        return Decision("call", comment=f"[pre] {tag} call")

    # RAISE — size based on position and opponents
    raise_to = _preflop_raise_size(position, min_raise, our_chips, opp_profiles)

    if raise_to >= our_chips:
        if tier == HandTier.PREMIUM:
            return Decision("all_in", comment=f"[pre] {tag} jam")
        # Don't jam non-premium — just call or make a smaller raise
        if amount_to_call == 0:
            return Decision("check", comment=f"[pre] {tag} pot control")
        return Decision("call", comment=f"[pre] {tag} call instead")

    if amount_to_call == 0:
        return Decision("bet", amount=raise_to, comment=f"[pre] {tag} open")
    return Decision("raise", amount=raise_to, comment=f"[pre] {tag} 3bet")


def _preflop_raise_size(
    position: Position,
    min_raise: int,
    our_chips: int,
    opp_profiles: list[OpponentProfile],
) -> int:
    """Variable preflop raise sizing."""
    base = BIG_BLIND * 3  # Standard 3x open

    # Add 1BB per limper/caller (approximate from pot)
    # Late position can open smaller
    if position == Position.LATE:
        base = max(int(BIG_BLIND * 2.5), min_raise)
    elif position == Position.EARLY:
        base = max(BIG_BLIND * 3, min_raise)

    # Against loose opponents, size up to punish wide calling ranges
    if any(p.is_loose for p in opp_profiles):
        base = max(base, int(BIG_BLIND * 3.5))

    return max(base, min_raise)


def _adjusted_preflop_action(
    tier: HandTier,
    position: Position,
    facing_raise: bool,
    opp_profiles: list[OpponentProfile],
) -> PreflopAction:
    """Adjust preflop action based on opponent tendencies."""
    base = preflop_action(tier, position, facing_raise)

    # Against very passive opponents, widen our raising range
    if all(p.is_passive for p in opp_profiles if p.hands_seen >= 5):
        if base == PreflopAction.CALL and tier == HandTier.PLAYABLE:
            return PreflopAction.RAISE
        if base == PreflopAction.FOLD and tier == HandTier.MARGINAL and position == Position.LATE:
            return PreflopAction.CALL

    # Against aggressive opponents with high fold-to-raise, bluff more
    if any(p.fold_to_raise_pct > 0.6 and p.hands_seen >= 8 for p in opp_profiles):
        if base == PreflopAction.FOLD and tier == HandTier.MARGINAL:
            return PreflopAction.RAISE  # light 3-bet bluff

    # Against loose opponents, tighten calling range but widen value raises
    if any(p.is_loose for p in opp_profiles):
        if base == PreflopAction.CALL and tier == HandTier.MARGINAL:
            return PreflopAction.FOLD  # don't play marginal vs loose

    return base


# ── Postflop ─────────────────────────────────────────


def _postflop(
    state: dict[str, Any],
    hole: tuple[str, ...],
    community: tuple[str, ...],
    pot: int,
    amount_to_call: int,
    min_raise: int,
    our_chips: int,
) -> Decision:
    """Postflop: equity + board texture + opponent reads."""
    active_opps = _count_active_opponents(state)
    equity = estimate_equity(
        hole=(hole[0], hole[1]),
        community=community,
        num_opponents=max(active_opps, 1),
    )

    board = analyze_board(community)
    opp_profiles = _get_opponent_profiles(state)
    pot_odds = amount_to_call / (pot + amount_to_call) if amount_to_call > 0 else 0.0
    position = _get_position(state)
    spr = our_chips / max(pot, 1)  # stack-to-pot ratio

    # Hand strength qualifiers
    have_flush = has_flush((hole[0], hole[1]), community)
    have_flush_draw = has_flush_draw((hole[0], hole[1]), community)
    have_oesd = has_open_ended_straight_draw((hole[0], hole[1]), community)
    have_overpair = has_overpair((hole[0], hole[1]), community)
    have_top_pair = has_top_pair((hole[0], hole[1]), community)
    tp_kicker = top_pair_kicker_strength((hole[0], hole[1]), community)

    # Adjust equity thresholds based on board texture
    danger = _board_danger(board)  # 0.0 = dry, 1.0 = very wet/scary
    tag = f"eq={equity:.0%} po={pot_odds:.0%} d={danger:.1f}"

    # ── Monster hands (equity >= 80%) ────────────────
    if equity >= 0.80:
        return _play_monster(
            pot, min_raise, our_chips, amount_to_call, spr, opp_profiles, tag,
        )

    # ── Strong hands (equity >= 65%) ─────────────────
    if equity >= 0.65:
        return _play_strong(
            pot, min_raise, our_chips, amount_to_call, spr,
            board, opp_profiles, position, tag,
        )

    # ── Drawing hands (flush draw or OESD) ───────────
    if (have_flush_draw or have_oesd) and equity >= 0.30:
        return _play_draw(
            pot, min_raise, our_chips, amount_to_call,
            equity, pot_odds, opp_profiles, board, tag,
        )

    # ── Decent hands (equity >= 50%) ─────────────────
    if equity >= 0.50:
        return _play_decent(
            pot, min_raise, our_chips, amount_to_call,
            board, opp_profiles, position, tag,
        )

    # ── Marginal but +EV call ────────────────────────
    if equity >= pot_odds + 0.05 and amount_to_call > 0:
        # But not if board is very dangerous and opponent is aggressive
        if danger > 0.6 and any(p.is_aggressive for p in opp_profiles):
            if amount_to_call > pot * 0.5:
                return Decision("fold", comment=f"[post] {tag} scary board")
        if amount_to_call >= our_chips:
            # Only all-in call with decent equity
            if equity >= 0.40:
                return Decision("all_in", comment=f"[post] {tag} committed")
            return Decision("fold", comment=f"[post] {tag} not enough eq to jam")
        return Decision("call", comment=f"[post] {tag} +EV call")

    # ── Bluff opportunities ──────────────────────────
    bluff = _consider_bluff(
        state, pot, min_raise, our_chips, amount_to_call,
        equity, board, opp_profiles, position,
    )
    if bluff is not None:
        return bluff

    # ── Weak hand ────────────────────────────────────
    if amount_to_call == 0:
        return Decision("check", comment=f"[post] {tag} weak check")
    return Decision("fold", comment=f"[post] {tag} fold")


def _play_monster(
    pot: int, min_raise: int, our_chips: int, amount_to_call: int,
    spr: float, opp_profiles: list[OpponentProfile], tag: str,
) -> Decision:
    """Play a very strong hand — extract maximum value."""
    # Low SPR or short-stacked: just jam
    if spr < 2.0:
        return Decision("all_in", comment=f"[post] {tag} low-SPR jam")

    # Against passive opponents: bet big, they'll call with worse
    if any(p.is_passive for p in opp_profiles):
        bet_frac = 0.85
    else:
        bet_frac = 0.70  # Standard value bet

    target = max(min_raise, int(pot * bet_frac))
    if target >= our_chips:
        return Decision("all_in", comment=f"[post] {tag} value jam")

    if amount_to_call == 0:
        return Decision("bet", amount=target, comment=f"[post] {tag} value bet")
    if target <= amount_to_call:
        return Decision("call", comment=f"[post] {tag} slowplay call")
    return Decision("raise", amount=target, comment=f"[post] {tag} value raise")


def _play_strong(
    pot: int, min_raise: int, our_chips: int, amount_to_call: int,
    spr: float, board: BoardTexture, opp_profiles: list[OpponentProfile],
    position: Position, tag: str,
) -> Decision:
    """Play a strong hand — value bet but protect on wet boards."""
    # On wet boards, bet larger to deny draws
    if board.has_straight_draw or board.is_two_tone:
        bet_frac = 0.75
    else:
        bet_frac = 0.55  # Dry board: smaller to induce calls

    # In position with strong hand on dry board: sometimes check back for deception
    # (only do this ~30% of the time conceptually — we approximate by checking
    # when community is exactly 3 cards and board is very dry)
    if (
        position == Position.LATE
        and amount_to_call == 0
        and not board.has_straight_draw
        and board.is_rainbow
        and board.num_community == 3
    ):
        # Trap: check back the flop, plan to bet turn
        return Decision("check", comment=f"[post] {tag} trap check")

    target = max(min_raise, int(pot * bet_frac))
    if target >= our_chips:
        return Decision("all_in", comment=f"[post] {tag} strong jam")

    if amount_to_call == 0:
        return Decision("bet", amount=target, comment=f"[post] {tag} strong bet")
    if target <= amount_to_call:
        if amount_to_call >= our_chips:
            return Decision("all_in", comment=f"[post] {tag} strong call-jam")
        return Decision("call", comment=f"[post] {tag} strong call")
    return Decision("raise", amount=target, comment=f"[post] {tag} strong raise")


def _play_draw(
    pot: int, min_raise: int, our_chips: int, amount_to_call: int,
    equity: float, pot_odds: float, opp_profiles: list[OpponentProfile],
    board: BoardTexture, tag: str,
) -> Decision:
    """Play a draw — semi-bluff when appropriate, call when odds are right."""
    # Semi-bluff: bet/raise with draws to put pressure + win with hand improvement
    if amount_to_call == 0:
        # Bet as semi-bluff ~60% pot
        target = max(min_raise, int(pot * 0.60))
        if target >= our_chips:
            # Don't jam a draw unless equity is very high
            if equity >= 0.45:
                return Decision("all_in", comment=f"[post] {tag} draw jam")
            return Decision("check", comment=f"[post] {tag} draw check")
        return Decision("bet", amount=target, comment=f"[post] {tag} semi-bluff")

    # Facing a bet: call if we have odds, raise as semi-bluff vs timid opponents
    if equity >= pot_odds:
        # Check-raise semi-bluff against passive opponents
        if (
            any(p.fold_to_raise_pct > 0.5 for p in opp_profiles if p.hands_seen >= 5)
            and amount_to_call < our_chips * 0.3
        ):
            raise_to = max(min_raise, int(pot * 0.80))
            if raise_to < our_chips:
                return Decision("raise", amount=raise_to, comment=f"[post] {tag} draw c/r")

        if amount_to_call >= our_chips:
            if equity >= 0.40:
                return Decision("all_in", comment=f"[post] {tag} draw all-in")
            return Decision("fold", comment=f"[post] {tag} draw too much")
        return Decision("call", comment=f"[post] {tag} draw call")

    # Not getting odds — fold unless implied odds are huge
    if amount_to_call <= pot * 0.25 and equity >= 0.25:
        return Decision("call", comment=f"[post] {tag} implied odds")

    return Decision("fold", comment=f"[post] {tag} draw fold")


def _play_decent(
    pot: int, min_raise: int, our_chips: int, amount_to_call: int,
    board: BoardTexture, opp_profiles: list[OpponentProfile],
    position: Position, tag: str,
) -> Decision:
    """Play a decent hand — thin value or pot control."""
    if amount_to_call == 0:
        # Value bet on dry boards in position
        if not board.has_straight_draw and board.is_rainbow and position in (Position.LATE, Position.MIDDLE):
            target = max(min_raise, int(pot * 0.45))
            if target < our_chips:
                return Decision("bet", amount=target, comment=f"[post] {tag} thin value")
        return Decision("check", comment=f"[post] {tag} pot control")

    # Facing a bet
    if amount_to_call >= our_chips:
        return Decision("fold", comment=f"[post] {tag} too much for decent hand")
    return Decision("call", comment=f"[post] {tag} decent call")


def _consider_bluff(
    state: dict[str, Any],
    pot: int, min_raise: int, our_chips: int, amount_to_call: int,
    equity: float, board: BoardTexture, opp_profiles: list[OpponentProfile],
    position: Position,
) -> Decision | None:
    """Consider bluffing — only in favorable spots."""
    # Only bluff when we're the aggressor (not facing a bet) and in position
    if amount_to_call > 0:
        return None
    if position not in (Position.LATE, Position.MIDDLE):
        return None

    # Don't bluff with too many opponents
    active = _count_active_opponents(state)
    if active > 2:
        return None

    # Bluff on scary boards (high cards, paired, straight-looking)
    # when opponents are likely to fold
    fold_happy = any(
        p.fold_to_raise_pct > 0.5 and p.hands_seen >= 5
        for p in opp_profiles
    )

    if not fold_happy and not (board.is_paired or board.high_card_rank >= 10):
        return None

    # River bluff: represent the missed draw that got there
    if board.num_community == 5:
        if board.is_two_tone or board.has_straight_draw:
            target = max(min_raise, int(pot * 0.65))
            if target < our_chips * 0.3:  # Don't risk too much on a bluff
                return Decision("bet", amount=target, comment=f"[bluff] river rep")

    # C-bet bluff on flop (we were the preflop raiser concept — approximate)
    if board.num_community == 3:
        if board.high_card_rank >= 10 and board.is_rainbow:
            target = max(min_raise, int(pot * 0.50))
            if target < our_chips * 0.2:
                return Decision("bet", amount=target, comment=f"[bluff] cbet")

    return None


# ── Helpers ──────────────────────────────────────────


def _board_danger(board: BoardTexture) -> float:
    """Rate board danger from 0.0 (dry) to 1.0 (very wet)."""
    danger = 0.0
    if board.is_monotone:
        danger += 0.4
    elif board.is_two_tone:
        danger += 0.15
    if board.has_straight_draw:
        danger += 0.2
    if board.is_connected:
        danger += 0.1
    if board.is_paired:
        danger += 0.1
    if board.is_double_paired or board.is_trip_board:
        danger += 0.2
    return min(danger, 1.0)


def _get_position(state: dict[str, Any]) -> Position:
    players = state["players"]
    all_ids = tuple(p["id"] for p in players if not p.get("is_resigned", False))
    our_id = state["current_turn"]
    dealer_id = state["dealer"]
    return determine_position(our_id, dealer_id, all_ids)


def _count_active_opponents(state: dict[str, Any]) -> int:
    our_id = state["current_turn"]
    return sum(
        1
        for p in state["players"]
        if p["id"] != our_id and not p["is_folded"] and not p.get("is_resigned", False)
    )


def _get_opponent_profiles(state: dict[str, Any]) -> list[OpponentProfile]:
    """Get profiles for all active opponents."""
    our_id = state["current_turn"]
    profiles = []
    for p in state["players"]:
        if p["id"] != our_id and not p["is_folded"] and not p.get("is_resigned", False):
            profiles.append(_tracker.profile(p["name"]))
    return profiles
