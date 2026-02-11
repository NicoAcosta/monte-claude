"""Hawk strategy: mathematically optimal TAG (Tight-Aggressive) bot.

Hawk is the most mathematically precise player at the table:
- Extremely tight preflop -- only plays premium and strong hands, but plays them HARD
- Precise pot odds and implied odds calculations for every decision
- Kelly criterion-inspired bet sizing to maximize long-term growth rate
- Explicit SPR (stack-to-pot ratio) commitment thresholds
- Reverse implied odds awareness -- avoids dominated hands
- ICM-like chip pressure against short-stacked opponents
- Every chip risked must have positive expected value
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..equity import estimate_equity
from ..cards import rank_index, is_suited, is_pair, gap
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

# Global tracker persists across calls within one game session.
_tracker = OpponentTracker()


@dataclass(frozen=True)
class Decision:
    action: str
    amount: int | None = None
    comment: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decide(state: dict[str, Any]) -> Decision:
    """Main entry point: state dict -> Decision."""
    _tracker.update(state)

    phase = state["phase"]
    hole = tuple(state["your_cards"])
    community = tuple(state["community_cards"])
    pot = state["pot"]
    amount_to_call = state["amount_to_call"]
    min_raise = state["min_raise"]
    our_chips = state["your_chips"]

    if phase == "preflop":
        return _preflop(state, hole, amount_to_call, min_raise, our_chips, pot)
    return _postflop(state, hole, community, pot, amount_to_call, min_raise, our_chips)


def reset_tracker() -> None:
    """Reset the global opponent tracker (for new games)."""
    global _tracker
    _tracker = OpponentTracker()


# =====================================================================
# MATH TOOLKIT
# =====================================================================

def _pot_odds(amount_to_call: int, pot: int) -> float:
    """Minimum equity needed to profitably call.

    pot_odds = cost / (pot + cost)
    """
    if amount_to_call <= 0:
        return 0.0
    return amount_to_call / (pot + amount_to_call)


def _effective_stack(our_chips: int, state: dict[str, Any]) -> int:
    """Effective stack = min(our chips, largest active opponent stack).

    This is the maximum we can win/lose in a single hand.
    """
    our_id = state["current_turn"]
    opp_chips = [
        p["chips"]
        for p in state["players"]
        if p["id"] != our_id and not p["is_folded"] and not p.get("is_resigned", False)
    ]
    if not opp_chips:
        return our_chips
    return min(our_chips, max(opp_chips))


def _spr(our_chips: int, pot: int) -> float:
    """Stack-to-pot ratio. Drives commitment decisions.

    SPR < 3  -> committed with top pair+
    SPR < 6  -> committed with overpair+
    SPR > 10 -> need very strong hand to stack off
    """
    return our_chips / max(pot, 1)


def _implied_odds_multiplier(our_chips: int, pot: int, phase: str) -> float:
    """Return a multiplier >= 1.0 that inflates raw equity to account for
    implied odds -- the extra chips we expect to win on later streets when
    we hit our draw.

    Deep stacks + early street = large implied odds.
    """
    spr = _spr(our_chips, pot)
    streets_left = {"flop": 2, "turn": 1, "river": 0}.get(phase, 0)
    if streets_left == 0:
        return 1.0  # River: no future streets, no implied odds
    # Heuristic: deeper stacks and more streets left mean better implied odds.
    # Cap at 1.5x to avoid overvaluing weak draws.
    bonus = min(0.15 * streets_left * min(spr / 10.0, 1.0), 0.50)
    return 1.0 + bonus


def _reverse_implied_odds_discount(
    hole: tuple[str, ...],
    community: tuple[str, ...],
    equity: float,
    board: BoardTexture,
) -> float:
    """Discount equity for dominated-hand risk.

    Hands like KJ on a K-high board have reverse implied odds: when we
    are behind (opponent has KQ/AK), we lose a LOT more than we win from
    worse hands. Returns a multiplier in [0.7, 1.0].
    """
    if not community:
        return 1.0

    have_tp = has_top_pair((hole[0], hole[1]), community)
    tp_kicker = top_pair_kicker_strength((hole[0], hole[1]), community)

    # Weak top pair (kicker < J) on a wet board is risky.
    if have_tp and tp_kicker < 9 and (board.is_two_tone or board.has_straight_draw):
        return 0.85

    # Top pair with bad kicker on any board.
    if have_tp and tp_kicker < 7:
        return 0.80

    # Underpair on a board with overcards.
    hole_ranks = sorted([rank_index(hole[0]), rank_index(hole[1])], reverse=True)
    if is_pair(hole[0], hole[1]) and community:
        board_high = max(rank_index(c) for c in community)
        if hole_ranks[0] < board_high:
            # How many overcards on board?
            overcards = sum(1 for c in community if rank_index(c) > hole_ranks[0])
            if overcards >= 2:
                return 0.75
            return 0.85

    return 1.0


def _kelly_bet_size(equity: float, pot: int) -> int:
    """Kelly criterion-inspired bet sizing for value.

    Simplified Kelly for poker: bet = (2*equity - 1) * pot  when equity > 0.5
    This maximizes long-term bankroll growth rate. We clamp to reasonable
    poker bet sizes (33% pot to 120% pot).
    """
    if equity <= 0.50:
        return int(pot * 0.33)  # Minimum viable bet / thin value
    kelly_fraction = (2.0 * equity - 1.0)
    # Map kelly fraction to pot-relative bet size.
    # kelly_fraction = 0.0 -> 33% pot, 1.0 -> 120% pot
    bet_frac = 0.33 + kelly_fraction * 0.87
    bet_frac = max(0.33, min(bet_frac, 1.20))
    return max(1, int(pot * bet_frac))


def _ev_of_call(equity: float, pot: int, amount_to_call: int) -> float:
    """Expected value of calling.

    EV = equity * (pot + amount_to_call) - amount_to_call
    Positive EV means the call is profitable.
    """
    return equity * (pot + amount_to_call) - amount_to_call


def _ev_of_raise(
    equity: float, pot: int, raise_amount: int,
    fold_probability: float,
) -> float:
    """Expected value of raising, accounting for fold equity.

    EV = fold_prob * pot + (1 - fold_prob) * [equity * (pot + 2*raise) - raise]
    """
    ev_if_called = equity * (pot + 2 * raise_amount) - raise_amount
    ev_if_fold = pot
    return fold_probability * ev_if_fold + (1 - fold_probability) * ev_if_called


def _estimate_fold_probability(opp_profiles: list[OpponentProfile]) -> float:
    """Estimate average probability opponents fold to a raise."""
    if not opp_profiles:
        return 0.35  # Default assumption
    informed = [p for p in opp_profiles if p.hands_seen >= 3]
    if not informed:
        return 0.35
    return sum(p.fold_to_raise_pct for p in informed) / len(informed)


def _opponent_avg_vpip(opp_profiles: list[OpponentProfile]) -> float:
    """Average VPIP of opponents with enough data."""
    informed = [p for p in opp_profiles if p.hands_seen >= 5]
    if not informed:
        return 0.45  # default neutral assumption
    return sum(p.vpip for p in informed) / len(informed)


def _count_short_stacks(state: dict[str, Any], threshold_bb: int = 10) -> int:
    """Count opponents whose stack is below threshold_bb big blinds."""
    our_id = state["current_turn"]
    return sum(
        1
        for p in state["players"]
        if (
            p["id"] != our_id
            and not p["is_folded"]
            and not p.get("is_resigned", False)
            and p["chips"] < threshold_bb * BIG_BLIND
        )
    )


def _max_opponent_stack(state: dict[str, Any]) -> int:
    """Largest active opponent stack."""
    our_id = state["current_turn"]
    stacks = [
        p["chips"]
        for p in state["players"]
        if p["id"] != our_id and not p["is_folded"] and not p.get("is_resigned", False)
    ]
    return max(stacks) if stacks else 0


# =====================================================================
# PREFLOP
# =====================================================================

def _preflop(
    state: dict[str, Any],
    hole: tuple[str, ...],
    amount_to_call: int,
    min_raise: int,
    our_chips: int,
    pot: int,
) -> Decision:
    """Hawk's preflop: extremely tight, extremely aggressive.

    Tighter than Shark's ranges -- folds marginal hands more often, but
    when it enters a pot, it enters raising.
    """
    tier = classify_hand(hole[0], hole[1])
    position = _get_position(state)
    facing_raise = amount_to_call > BIG_BLIND
    opp_profiles = _get_opponent_profiles(state)
    short_stacks = _count_short_stacks(state)
    eff_stack = _effective_stack(our_chips, state)
    eff_bb = eff_stack / BIG_BLIND

    tag = f"H:{tier.value}/{position.value}"

    # -- Hawk's TIGHTER preflop action selection --
    action = _hawk_preflop_action(tier, position, facing_raise, opp_profiles, eff_bb)

    # === FOLD ===
    if action == PreflopAction.FOLD:
        if amount_to_call == 0:
            return Decision("check", comment=f"[pre] {tag} check")
        return Decision("fold", comment=f"[pre] {tag} fold")

    # === CALL ===
    if action == PreflopAction.CALL:
        if amount_to_call == 0:
            # In position with a playable+ hand, raise to isolate rather than limp.
            if tier in (HandTier.PLAYABLE, HandTier.STRONG) and position == Position.LATE:
                raise_to = max(min_raise, int(BIG_BLIND * 2.5))
                if raise_to < our_chips:
                    return Decision("bet", amount=raise_to, comment=f"[pre] {tag} isolate")
            return Decision("check", comment=f"[pre] {tag} check")
        if amount_to_call >= our_chips:
            # All-in call: only with premium/strong
            if tier in (HandTier.PREMIUM, HandTier.STRONG):
                return Decision("all_in", comment=f"[pre] {tag} all-in call")
            return Decision("fold", comment=f"[pre] {tag} too expensive")
        # Pot odds check even preflop: is calling +EV?
        # With a call-worthy hand vs a raise, approximate equity vs raiser range
        approx_equity = _preflop_tier_equity(tier, facing_raise)
        call_ev = _ev_of_call(approx_equity, pot, amount_to_call)
        if call_ev < 0 and amount_to_call > BIG_BLIND * 4:
            return Decision("fold", comment=f"[pre] {tag} -EV call, fold")
        return Decision("call", comment=f"[pre] {tag} call EV={call_ev:+.0f}")

    # === RAISE ===
    raise_to = _hawk_preflop_raise_size(
        tier, position, min_raise, our_chips, pot, opp_profiles, short_stacks, eff_bb,
    )

    if raise_to >= our_chips:
        # Only jam premium; with strong, make a smaller raise or call.
        if tier == HandTier.PREMIUM:
            return Decision("all_in", comment=f"[pre] {tag} premium jam")
        if tier == HandTier.STRONG and eff_bb <= 15:
            # Short-stacked with strong hand: jam is fine.
            return Decision("all_in", comment=f"[pre] {tag} short-stack jam")
        # Otherwise, just call or check.
        if amount_to_call == 0:
            return Decision("check", comment=f"[pre] {tag} pot control")
        if amount_to_call < our_chips:
            return Decision("call", comment=f"[pre] {tag} call instead of jam")
        return Decision("fold", comment=f"[pre] {tag} can't raise, fold")

    if amount_to_call == 0:
        return Decision("bet", amount=raise_to, comment=f"[pre] {tag} open")
    return Decision("raise", amount=raise_to, comment=f"[pre] {tag} 3bet")


def _hawk_preflop_action(
    tier: HandTier,
    position: Position,
    facing_raise: bool,
    opp_profiles: list[OpponentProfile],
    eff_bb: float,
) -> PreflopAction:
    """Hawk's tighter preflop action table.

    Differences from standard ranges:
    - Folds MARGINAL from all positions (Shark sometimes calls/opens these).
    - Only opens PLAYABLE from LATE/MIDDLE (Shark opens from everywhere).
    - Against loose opponents, widens raising range for value.
    - Against very tight opponents, steals more aggressively.
    """
    # Start with standard range, then tighten.
    base = preflop_action(tier, position, facing_raise)

    # --- Hawk tightening ---
    # Never open or limp marginal hands. This is the core TAG identity.
    if tier == HandTier.MARGINAL:
        # Exception: in the blind with no raise, check is free.
        if not facing_raise and position == Position.BLIND:
            return PreflopAction.CALL  # We're already in -- free check
        # Exception: short-stacked (<15BB), push/fold mode.
        if eff_bb < 15 and tier == HandTier.MARGINAL:
            return PreflopAction.FOLD
        # Exception: late position steal vs tight opponents.
        if (
            not facing_raise
            and position == Position.LATE
            and all(p.is_tight for p in opp_profiles if p.hands_seen >= 8)
            and len([p for p in opp_profiles if p.hands_seen >= 8]) >= 1
        ):
            return PreflopAction.RAISE  # Steal attempt with marginal
        return PreflopAction.FOLD

    # PLAYABLE from early position vs raise: fold (tighter than Shark).
    if tier == HandTier.PLAYABLE and position == Position.EARLY and facing_raise:
        return PreflopAction.FOLD

    # --- Exploit adjustments ---
    # Against very loose opponents (VPIP > 55%), raise more for value.
    if any(p.is_loose for p in opp_profiles):
        if base == PreflopAction.CALL and tier in (HandTier.PLAYABLE, HandTier.STRONG):
            return PreflopAction.RAISE  # Raise for value against loose callers.

    # Against very passive opponents, raise wider for thin value.
    if all(p.is_passive for p in opp_profiles if p.hands_seen >= 5):
        if base == PreflopAction.CALL and tier == HandTier.PLAYABLE:
            return PreflopAction.RAISE

    # Against high fold-to-raise opponents, 3bet lighter.
    if any(p.fold_to_raise_pct > 0.65 and p.hands_seen >= 8 for p in opp_profiles):
        if base == PreflopAction.FOLD and tier == HandTier.PLAYABLE:
            return PreflopAction.RAISE  # Light 3bet as exploit.

    return base


def _preflop_tier_equity(tier: HandTier, facing_raise: bool) -> float:
    """Approximate preflop equity by tier vs opponent range.

    When facing a raise, opponent range is stronger, so our equity is lower.
    """
    base = {
        HandTier.PREMIUM: 0.78,
        HandTier.STRONG: 0.65,
        HandTier.PLAYABLE: 0.55,
        HandTier.MARGINAL: 0.45,
        HandTier.TRASH: 0.35,
    }[tier]
    if facing_raise:
        return base - 0.08  # Opponent range is tighter
    return base


def _hawk_preflop_raise_size(
    tier: HandTier,
    position: Position,
    min_raise: int,
    our_chips: int,
    pot: int,
    opp_profiles: list[OpponentProfile],
    short_stacks: int,
    eff_bb: float,
) -> int:
    """Kelly-inspired preflop raise sizing.

    Instead of arbitrary 3x, Hawk sizes based on:
    1. Hand equity (premium -> larger to build pot)
    2. Position (IP can size smaller)
    3. Opponent tendencies (loose callers -> size up)
    4. ICM pressure (short stacks -> size to put them all-in)
    """
    # Approximate equity for Kelly sizing.
    eq = _preflop_tier_equity(tier, facing_raise=False)

    # Base Kelly size: (2*eq - 1) * pot. But preflop pot is small,
    # so we use BB multiples as a floor.
    kelly_size = max(1, int((2.0 * eq - 1.0) * max(pot, BIG_BLIND * 4)))

    # Minimum open sizes by position.
    if position == Position.LATE:
        floor = int(BIG_BLIND * 2.2)
    elif position == Position.MIDDLE:
        floor = int(BIG_BLIND * 2.5)
    else:
        floor = BIG_BLIND * 3

    base = max(kelly_size, floor, min_raise)

    # Size up against loose opponents (they call too wide, we get value).
    if any(p.is_loose for p in opp_profiles):
        base = max(base, int(BIG_BLIND * 3.5))

    # Premium hands: size up to build pot.
    if tier == HandTier.PREMIUM:
        base = max(base, int(BIG_BLIND * 3.5))

    # ICM pressure: if an opponent has < 10BB, size to put them all-in.
    if short_stacks > 0:
        # Find the smallest short-stack opponent.
        min_short = BIG_BLIND * 10  # threshold
        base = max(base, min_short)

    # Push/fold: if we're short (<15BB), just jam with raising hands.
    if eff_bb < 15 and tier in (HandTier.PREMIUM, HandTier.STRONG):
        return our_chips  # Will be caught as all-in in caller.

    return max(base, min_raise)


# =====================================================================
# POSTFLOP
# =====================================================================

def _postflop(
    state: dict[str, Any],
    hole: tuple[str, ...],
    community: tuple[str, ...],
    pot: int,
    amount_to_call: int,
    min_raise: int,
    our_chips: int,
) -> Decision:
    """Hawk's postflop: pure math-driven decisions."""
    active_opps = _count_active_opponents(state)
    equity = estimate_equity(
        hole=(hole[0], hole[1]),
        community=community,
        num_opponents=max(active_opps, 1),
    )

    board = analyze_board(community)
    opp_profiles = _get_opponent_profiles(state)
    position = _get_position(state)
    phase = state["phase"]

    pot_odds_val = _pot_odds(amount_to_call, pot)
    spr_val = _spr(our_chips, pot)
    eff_stack = _effective_stack(our_chips, state)

    # Hand strength qualifiers.
    have_flush = has_flush((hole[0], hole[1]), community)
    have_flush_draw = has_flush_draw((hole[0], hole[1]), community)
    have_oesd = has_open_ended_straight_draw((hole[0], hole[1]), community)
    have_overpair = has_overpair((hole[0], hole[1]), community)
    have_top_pair = has_top_pair((hole[0], hole[1]), community)
    tp_kicker = top_pair_kicker_strength((hole[0], hole[1]), community)

    # Apply reverse implied odds discount.
    rio_discount = _reverse_implied_odds_discount(hole, community, equity, board)
    adjusted_equity = equity * rio_discount

    # Apply implied odds multiplier for drawing hands.
    implied_mult = 1.0
    if have_flush_draw or have_oesd:
        implied_mult = _implied_odds_multiplier(our_chips, pot, phase)

    # The effective equity used for all decisions.
    effective_equity = adjusted_equity * implied_mult

    # Board danger rating.
    danger = _board_danger(board)

    # Fold probability estimate.
    fold_prob = _estimate_fold_probability(opp_profiles)

    tag = (
        f"eq={equity:.0%} adj={effective_equity:.0%} "
        f"po={pot_odds_val:.0%} spr={spr_val:.1f} d={danger:.1f}"
    )

    # ================================================================
    # COMMITMENT CHECK (SPR-based)
    # ================================================================
    # If SPR is low, we're pot-committed. Simplify decisions.
    if spr_val < 2.0 and amount_to_call > 0:
        return _committed_decision(
            effective_equity, pot, amount_to_call, our_chips, tag,
        )

    # ================================================================
    # MONSTER HANDS (equity >= 80%)
    # ================================================================
    if equity >= 0.80:
        return _play_monster(
            equity, pot, min_raise, our_chips, amount_to_call,
            spr_val, opp_profiles, tag,
        )

    # ================================================================
    # STRONG HANDS (equity >= 65%)
    # ================================================================
    if equity >= 0.65:
        return _play_strong(
            equity, effective_equity, pot, min_raise, our_chips, amount_to_call,
            spr_val, board, opp_profiles, position, phase, tag,
        )

    # ================================================================
    # DRAWING HANDS (flush draw or OESD with decent equity)
    # ================================================================
    if (have_flush_draw or have_oesd) and equity >= 0.25:
        return _play_draw(
            equity, effective_equity, pot, min_raise, our_chips, amount_to_call,
            pot_odds_val, spr_val, opp_profiles, board, phase, fold_prob, tag,
        )

    # ================================================================
    # MEDIUM HANDS (equity >= 50%)
    # ================================================================
    if equity >= 0.50:
        return _play_medium(
            equity, effective_equity, pot, min_raise, our_chips, amount_to_call,
            pot_odds_val, board, opp_profiles, position, spr_val, tag,
        )

    # ================================================================
    # MARGINAL HANDS (equity above pot odds -- pure math call)
    # ================================================================
    if amount_to_call > 0 and effective_equity > pot_odds_val:
        call_ev = _ev_of_call(effective_equity, pot, amount_to_call)
        if call_ev > 0:
            # Extra caution on dangerous boards vs aggressive opponents.
            if danger > 0.6 and any(p.is_aggressive for p in opp_profiles):
                if amount_to_call > pot * 0.5:
                    return Decision("fold", comment=f"[post] {tag} -EV vs aggro on wet board")
            if amount_to_call >= our_chips:
                if effective_equity >= 0.42:
                    return Decision("all_in", comment=f"[post] {tag} +EV committed call")
                return Decision("fold", comment=f"[post] {tag} not enough eq to jam")
            return Decision("call", comment=f"[post] {tag} +EV call ev={call_ev:+.0f}")

    # ================================================================
    # BLUFF OPPORTUNITIES
    # ================================================================
    bluff = _consider_bluff(
        state, equity, pot, min_raise, our_chips, amount_to_call,
        board, opp_profiles, position, fold_prob, phase, tag,
    )
    if bluff is not None:
        return bluff

    # ================================================================
    # WEAK HAND
    # ================================================================
    if amount_to_call == 0:
        return Decision("check", comment=f"[post] {tag} weak check")
    return Decision("fold", comment=f"[post] {tag} -EV fold")


# =====================================================================
# POSTFLOP HAND CATEGORIES
# =====================================================================

def _committed_decision(
    equity: float,
    pot: int,
    amount_to_call: int,
    our_chips: int,
    tag: str,
) -> Decision:
    """When SPR < 2, we're pot-committed. Jam or fold based on EV."""
    call_ev = _ev_of_call(equity, pot, amount_to_call)
    if call_ev >= 0 or equity >= 0.35:
        # Committed: any positive EV or 35%+ equity = go with it.
        return Decision("all_in", comment=f"[post] {tag} committed jam ev={call_ev:+.0f}")
    return Decision("fold", comment=f"[post] {tag} committed but -EV fold")


def _play_monster(
    equity: float,
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    spr: float,
    opp_profiles: list[OpponentProfile],
    tag: str,
) -> Decision:
    """Monster hand (80%+ equity): extract maximum value with Kelly sizing."""
    # Low SPR: just jam for value.
    if spr < 3.0:
        return Decision("all_in", comment=f"[post] {tag} monster low-SPR jam")

    # Kelly-inspired bet sizing.
    kelly_size = _kelly_bet_size(equity, pot)
    target = max(min_raise, kelly_size)

    # Against passive opponents who call too much, size up.
    if any(p.is_passive for p in opp_profiles):
        target = max(target, int(pot * 0.90))

    if target >= our_chips:
        return Decision("all_in", comment=f"[post] {tag} monster value jam")

    if amount_to_call == 0:
        return Decision("bet", amount=target, comment=f"[post] {tag} monster value bet")
    if target <= amount_to_call:
        # Facing a big bet with a monster: raise if possible, else call.
        reraise = max(min_raise, int((pot + amount_to_call) * 0.80))
        if reraise > amount_to_call and reraise < our_chips:
            return Decision("raise", amount=reraise, comment=f"[post] {tag} monster reraise")
        if amount_to_call >= our_chips:
            return Decision("all_in", comment=f"[post] {tag} monster snap call")
        return Decision("call", comment=f"[post] {tag} monster slowplay call")
    return Decision("raise", amount=target, comment=f"[post] {tag} monster value raise")


def _play_strong(
    equity: float,
    effective_equity: float,
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    spr: float,
    board: BoardTexture,
    opp_profiles: list[OpponentProfile],
    position: Position,
    phase: str,
    tag: str,
) -> Decision:
    """Strong hand (65-80% equity): value bet, protect on wet boards."""
    # SPR-based commitment: with SPR < 6, we're committed with strong hands.
    if spr < 4.0:
        if amount_to_call > 0:
            call_ev = _ev_of_call(effective_equity, pot, amount_to_call)
            if call_ev >= 0:
                if amount_to_call >= our_chips:
                    return Decision("all_in", comment=f"[post] {tag} strong committed jam")
                # Raise all-in to deny equity.
                return Decision("all_in", comment=f"[post] {tag} strong low-SPR jam")
        else:
            return Decision("all_in", comment=f"[post] {tag} strong low-SPR value jam")

    # Kelly bet sizing.
    kelly_size = _kelly_bet_size(equity, pot)

    # On wet boards, size up to deny draws equity.
    if board.has_straight_draw or board.is_two_tone:
        target = max(kelly_size, int(pot * 0.70))
    else:
        # Dry board: Kelly size (typically smaller for thin value).
        target = kelly_size

    target = max(min_raise, target)

    # In position on dry flop: consider a trap check to induce bluffs.
    if (
        position == Position.LATE
        and amount_to_call == 0
        and phase == "flop"
        and board.is_rainbow
        and not board.has_straight_draw
        and not board.is_connected
        and equity >= 0.70  # Only trap with very strong on truly dry boards
    ):
        return Decision("check", comment=f"[post] {tag} strong trap check")

    if target >= our_chips:
        return Decision("all_in", comment=f"[post] {tag} strong jam")

    if amount_to_call == 0:
        return Decision("bet", amount=target, comment=f"[post] {tag} strong value bet")
    if target <= amount_to_call:
        if amount_to_call >= our_chips:
            # Facing an all-in: call with strong hand.
            ev = _ev_of_call(effective_equity, pot, amount_to_call)
            if ev >= 0:
                return Decision("all_in", comment=f"[post] {tag} strong call-jam ev={ev:+.0f}")
            return Decision("fold", comment=f"[post] {tag} strong but -EV vs jam")
        return Decision("call", comment=f"[post] {tag} strong call")
    return Decision("raise", amount=target, comment=f"[post] {tag} strong raise")


def _play_draw(
    equity: float,
    effective_equity: float,
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    pot_odds: float,
    spr: float,
    opp_profiles: list[OpponentProfile],
    board: BoardTexture,
    phase: str,
    fold_prob: float,
    tag: str,
) -> Decision:
    """Drawing hand: semi-bluff when math supports it, call when odds are right."""
    # === Not facing a bet: consider semi-bluff ===
    if amount_to_call == 0:
        # Semi-bluff EV: fold_prob * pot + (1-fold_prob) * [equity * new_pot - bet]
        bluff_size = max(min_raise, int(pot * 0.55))
        raise_ev = _ev_of_raise(equity, pot, bluff_size, fold_prob)

        if raise_ev > 0 and bluff_size < our_chips:
            return Decision("bet", amount=bluff_size, comment=f"[post] {tag} semi-bluff ev={raise_ev:+.0f}")

        # Not +EV to bet: check and realize equity for free.
        return Decision("check", comment=f"[post] {tag} draw check")

    # === Facing a bet: pot odds + implied odds calculation ===
    call_ev = _ev_of_call(effective_equity, pot, amount_to_call)

    if call_ev > 0:
        # Check-raise semi-bluff: if fold equity makes it +EV.
        if (
            fold_prob > 0.40
            and amount_to_call < our_chips * 0.25
            and phase != "river"
        ):
            cr_size = max(min_raise, int((pot + amount_to_call) * 0.75))
            cr_ev = _ev_of_raise(equity, pot + amount_to_call, cr_size, fold_prob)
            if cr_ev > call_ev and cr_size < our_chips:
                return Decision("raise", amount=cr_size, comment=f"[post] {tag} draw c/r ev={cr_ev:+.0f}")

        if amount_to_call >= our_chips:
            if effective_equity >= 0.40:
                return Decision("all_in", comment=f"[post] {tag} draw all-in call")
            return Decision("fold", comment=f"[post] {tag} draw too much to call")
        return Decision("call", comment=f"[post] {tag} draw call ev={call_ev:+.0f}")

    # Negative EV call. Check for implied odds making it close.
    # On flop/turn with deep stacks, the implied odds multiplier may not
    # have been enough. Give a small extra allowance for very deep stacks.
    if phase != "river" and spr > 5.0 and amount_to_call <= pot * 0.30:
        # Cheap to call relative to implied future winnings.
        return Decision("call", comment=f"[post] {tag} draw implied odds call")

    return Decision("fold", comment=f"[post] {tag} draw -EV fold")


def _play_medium(
    equity: float,
    effective_equity: float,
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    pot_odds: float,
    board: BoardTexture,
    opp_profiles: list[OpponentProfile],
    position: Position,
    spr: float,
    tag: str,
) -> Decision:
    """Medium hand (50-65% equity): thin value or pot control."""
    if amount_to_call == 0:
        # Value bet on safe boards in position.
        if (
            position in (Position.LATE, Position.MIDDLE)
            and not board.is_two_tone
            and not board.has_straight_draw
        ):
            # Thin value: smaller sizing (33-50% pot via Kelly).
            target = _kelly_bet_size(equity, pot)
            target = max(min_raise, target)
            if target < our_chips:
                return Decision("bet", amount=target, comment=f"[post] {tag} thin value")

        # On wet/dangerous boards or out of position: pot control.
        return Decision("check", comment=f"[post] {tag} pot control")

    # Facing a bet: pure EV calculation.
    call_ev = _ev_of_call(effective_equity, pot, amount_to_call)

    if call_ev > 0:
        if amount_to_call >= our_chips:
            # All-in call only with decent equity edge.
            if effective_equity >= 0.50:
                return Decision("all_in", comment=f"[post] {tag} medium all-in ev={call_ev:+.0f}")
            return Decision("fold", comment=f"[post] {tag} medium not enough for jam")
        return Decision("call", comment=f"[post] {tag} medium +EV call ev={call_ev:+.0f}")

    # Negative EV: fold.
    return Decision("fold", comment=f"[post] {tag} medium -EV fold")


# =====================================================================
# BLUFFING
# =====================================================================

def _consider_bluff(
    state: dict[str, Any],
    equity: float,
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    board: BoardTexture,
    opp_profiles: list[OpponentProfile],
    position: Position,
    fold_prob: float,
    phase: str,
    tag: str,
) -> Decision | None:
    """Math-backed bluffing: only bluff when fold_equity makes it +EV.

    Bluff frequency is derived from: bluff_EV = fold_prob * pot - (1 - fold_prob) * bet
    We bluff when bluff_EV > 0 => fold_prob > bet / (pot + bet).
    """
    # Only bluff as aggressor (not facing a bet).
    if amount_to_call > 0:
        return None

    # Only bluff from position or heads-up.
    active = _count_active_opponents(state)
    if active > 2:
        return None
    if position not in (Position.LATE, Position.MIDDLE) and active > 1:
        return None

    # Need enough fold equity data.
    if fold_prob < 0.30:
        return None

    # --- River bluff: represent a completed draw ---
    if phase == "river" and (board.is_two_tone or board.has_straight_draw):
        bluff_size = max(min_raise, int(pot * 0.60))
        # bluff_EV = fold_prob * pot - (1 - fold_prob) * bluff_size
        bluff_ev = fold_prob * pot - (1.0 - fold_prob) * bluff_size
        if bluff_ev > 0 and bluff_size < our_chips * 0.25:
            return Decision("bet", amount=bluff_size,
                            comment=f"[bluff] {tag} river rep ev={bluff_ev:+.0f}")

    # --- Flop c-bet bluff: high cards favor preflop raiser ---
    if phase == "flop" and board.high_card_rank >= 9 and board.is_rainbow:
        cbet_size = max(min_raise, int(pot * 0.40))
        bluff_ev = fold_prob * pot - (1.0 - fold_prob) * cbet_size
        if bluff_ev > 0 and cbet_size < our_chips * 0.15:
            return Decision("bet", amount=cbet_size,
                            comment=f"[bluff] {tag} cbet ev={bluff_ev:+.0f}")

    # --- Turn probe: unimproved board after checked flop ---
    if phase == "turn" and board.is_rainbow and not board.is_connected:
        probe_size = max(min_raise, int(pot * 0.45))
        bluff_ev = fold_prob * pot - (1.0 - fold_prob) * probe_size
        if bluff_ev > 0 and probe_size < our_chips * 0.18:
            return Decision("bet", amount=probe_size,
                            comment=f"[bluff] {tag} turn probe ev={bluff_ev:+.0f}")

    return None


# =====================================================================
# HELPERS
# =====================================================================

def _board_danger(board: BoardTexture) -> float:
    """Rate board danger from 0.0 (dry) to 1.0 (very wet/scary)."""
    danger = 0.0
    if board.is_monotone:
        danger += 0.40
    elif board.is_two_tone:
        danger += 0.15
    if board.has_straight_draw:
        danger += 0.20
    if board.is_connected:
        danger += 0.10
    if board.is_paired:
        danger += 0.10
    if board.is_double_paired or board.is_trip_board:
        danger += 0.20
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
