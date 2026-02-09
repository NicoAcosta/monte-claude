"""Decision engine: preflop charts + postflop equity-based play."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .equity import estimate_equity
from .preflop_ranges import (
    HandTier,
    Position,
    PreflopAction,
    classify_hand,
    determine_position,
    preflop_action,
)

BIG_BLIND = 20


@dataclass(frozen=True)
class Decision:
    action: str
    amount: int | None = None
    comment: str | None = None


def decide(state: dict[str, Any]) -> Decision:
    """Core decision function: state dict → (action, amount, comment)."""
    phase = state["phase"]
    hole = tuple(state["your_cards"])
    community = tuple(state["community_cards"])
    pot = state["pot"]
    amount_to_call = state["amount_to_call"]
    min_raise = state["min_raise"]
    our_chips = state["your_chips"]
    if phase == "preflop":
        return _preflop_decide(state, hole, amount_to_call, min_raise, our_chips)
    return _postflop_decide(
        hole, community, pot, amount_to_call, min_raise, our_chips, state,
    )


def _preflop_decide(
    state: dict[str, Any],
    hole: tuple[str, ...],
    amount_to_call: int,
    min_raise: int,
    our_chips: int,
) -> Decision:
    """Preflop: use static chart lookup."""
    tier = classify_hand(hole[0], hole[1])
    position = _get_position(state)
    facing_raise = amount_to_call > BIG_BLIND

    action = preflop_action(tier, position, facing_raise)
    comment = f"[preflop] {tier.value} hand, {position.value} pos"

    if action == PreflopAction.FOLD:
        if amount_to_call == 0:
            return Decision("check", comment=comment)
        return Decision("fold", comment=comment)

    if action == PreflopAction.CALL:
        if amount_to_call == 0:
            return Decision("check", comment=comment)
        if amount_to_call >= our_chips:
            # Need to go all-in to call
            if tier in (HandTier.PREMIUM, HandTier.STRONG):
                return Decision("all_in", comment=comment)
            return Decision("fold", comment=comment)
        return Decision("call", comment=comment)

    # RAISE
    raise_to = max(min_raise, BIG_BLIND * 3)
    if raise_to >= our_chips:
        return Decision("all_in", comment=comment)

    if amount_to_call == 0:
        return Decision("bet", amount=raise_to, comment=comment)
    return Decision("raise", amount=raise_to, comment=comment)


def _postflop_decide(
    hole: tuple[str, ...],
    community: tuple[str, ...],
    pot: int,
    amount_to_call: int,
    min_raise: int,
    our_chips: int,
    state: dict[str, Any],
) -> Decision:
    """Postflop: Monte Carlo equity → threshold-based decision."""
    active_opponents = _count_active_opponents(state)
    equity = estimate_equity(
        hole=(hole[0], hole[1]),
        community=community,
        num_opponents=max(active_opponents, 1),
    )

    pot_odds = amount_to_call / (pot + amount_to_call) if amount_to_call > 0 else 0.0
    comment = f"[equity={equity:.0%} pot_odds={pot_odds:.0%}]"

    # Strong hand: bet/raise ~75% pot
    if equity >= 0.70:
        return _make_aggressive_action(
            pot, 0.75, min_raise, our_chips, amount_to_call, comment,
        )

    # Decent hand: bet ~50% pot or call
    if equity >= 0.50:
        if amount_to_call == 0:
            bet_size = max(min_raise, int(pot * 0.5))
            if bet_size >= our_chips:
                return Decision("all_in", comment=comment)
            return Decision("bet", amount=bet_size, comment=comment)
        return Decision("call", comment=comment)

    # Marginal but +EV: call
    if equity >= pot_odds + 0.05 and amount_to_call > 0:
        if amount_to_call >= our_chips:
            return Decision("all_in", comment=comment)
        return Decision("call", comment=comment)

    # Weak hand
    if amount_to_call == 0:
        return Decision("check", comment=comment)
    return Decision("fold", comment=comment)


def _make_aggressive_action(
    pot: int,
    bet_fraction: float,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    comment: str,
) -> Decision:
    """Build a bet or raise at a fraction of pot."""
    target = max(min_raise, int(pot * bet_fraction))

    if target >= our_chips:
        return Decision("all_in", comment=comment)

    if amount_to_call == 0:
        return Decision("bet", amount=target, comment=comment)
    if target <= amount_to_call:
        # Can't raise to less than call — just call
        return Decision("call", comment=comment)
    return Decision("raise", amount=target, comment=comment)


def _get_position(state: dict[str, Any]) -> Position:
    """Extract position from game state."""
    players = state["players"]
    active_ids = tuple(
        p["id"] for p in players if not p["is_folded"] and not p["is_resigned"]
    )
    # We need our own player_id — find it from whose turn it is (it's ours)
    our_id = state["current_turn"]
    dealer_id = state["dealer"]
    return determine_position(our_id, dealer_id, active_ids)


def _count_active_opponents(state: dict[str, Any]) -> int:
    """Count non-folded, non-resigned opponents."""
    our_id = state["current_turn"]
    return sum(
        1
        for p in state["players"]
        if p["id"] != our_id and not p["is_folded"] and not p["is_resigned"]
    )
