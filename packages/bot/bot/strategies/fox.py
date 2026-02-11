"""Fox strategy: deceptive, tricky, unpredictable poker bot.

Fox is the hardest opponent to read at the table:
- Slow-plays monsters to let opponents build the pot, then springs the trap
- Check-raises frequently to build pots out of position
- Mixed strategies: the same hand strength does not always produce the same action
- Reverse bet sizing: small bets with strong hands (to induce), big bets as bluffs
- Float plays: calls in position with nothing on flop, takes the pot on the turn
- Probe bets: small bets on scare cards to steal pots
- Varies bet sizing unpredictably (33% pot, 66% pot, 120% pot)
- Exploits opponents who only bet when they have it (traps the aggressor)
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

# Track our own recent actions per hand for check-raise and float detection
_hand_state: dict[str, Any] = {
    "hand_number": -1,
    "our_actions": [],       # actions we took this hand
    "phases_seen": set(),    # phases we acted in
    "was_preflop_raiser": False,
    "flop_action": None,     # what we did on the flop (for float tracking)
}


@dataclass(frozen=True)
class Decision:
    action: str
    amount: int | None = None
    comment: str | None = None


def _mix(state: dict[str, Any]) -> int:
    """Deterministic pseudo-random value 0-99 for mixing strategies.

    Uses hand number and pot as entropy sources so the same situation
    in the same hand/pot produces the same decision (reproducible),
    but varies across hands and pot sizes.
    """
    return (state["hand_number"] * 7 + state["pot"] * 13) % 100


def _update_hand_state(state: dict[str, Any]) -> None:
    """Track our own actions for multi-street planning (floats, check-raises)."""
    global _hand_state
    hand = state.get("hand_number", 0)
    if hand != _hand_state["hand_number"]:
        _hand_state = {
            "hand_number": hand,
            "our_actions": [],
            "phases_seen": set(),
            "was_preflop_raiser": False,
            "flop_action": None,
        }


def decide(state: dict[str, Any]) -> Decision:
    """Main entry point: state dict -> Decision."""
    _tracker.update(state)
    _update_hand_state(state)

    phase = state["phase"]
    hole = tuple(state["your_cards"])
    community = tuple(state["community_cards"])
    pot = state["pot"]
    amount_to_call = state["amount_to_call"]
    min_raise = state["min_raise"]
    our_chips = state["your_chips"]

    if phase == "preflop":
        dec = _preflop(state, hole, amount_to_call, min_raise, our_chips)
    else:
        dec = _postflop(state, hole, community, pot, amount_to_call, min_raise, our_chips)

    # Record our action for multi-street planning
    _hand_state["our_actions"].append(dec.action)
    _hand_state["phases_seen"].add(phase)
    if phase == "preflop" and dec.action in ("bet", "raise", "all_in"):
        _hand_state["was_preflop_raiser"] = True
    if phase == "flop":
        _hand_state["flop_action"] = dec.action

    return dec


def reset_tracker() -> None:
    """Reset the global opponent tracker (for new games)."""
    global _tracker, _hand_state
    _tracker = OpponentTracker()
    _hand_state = {
        "hand_number": -1,
        "our_actions": [],
        "phases_seen": set(),
        "was_preflop_raiser": False,
        "flop_action": None,
    }


# ---------------------------------------------------------------------------
#  Preflop
# ---------------------------------------------------------------------------

def _preflop(
    state: dict[str, Any],
    hole: tuple[str, ...],
    amount_to_call: int,
    min_raise: int,
    our_chips: int,
) -> Decision:
    """Preflop with deceptive sizing and trapping tendencies."""
    tier = classify_hand(hole[0], hole[1])
    position = _get_position(state)
    facing_raise = amount_to_call > BIG_BLIND
    opp_profiles = _get_opponent_profiles(state)
    mix = _mix(state)
    tag = f"{tier.value}/{position.value}"

    # Fox twist #1: With PREMIUM hands facing a raise, sometimes just FLAT CALL
    # to disguise strength (slow-play preflop). Do this ~40% of the time.
    if tier == HandTier.PREMIUM and facing_raise and mix < 40:
        if amount_to_call >= our_chips:
            return Decision("all_in", comment=f"[fox pre] {tag} premium jam")
        return Decision("call", comment=f"[fox pre] {tag} premium trap flat")

    # Fox twist #2: With MARGINAL hands in late position, sometimes raise to steal
    # (light 3-bet bluff ~35% of the time vs tight opponents)
    if tier == HandTier.MARGINAL and position == Position.LATE and not facing_raise:
        if any(p.is_tight for p in opp_profiles) or mix < 35:
            raise_to = max(min_raise, int(BIG_BLIND * 2.5))
            if raise_to < our_chips:
                return Decision("bet", amount=raise_to, comment=f"[fox pre] {tag} steal")

    # Fox twist #3: With MARGINAL hands, sometimes limp-reraise as a trap
    # if we expect someone behind to raise (from blinds, ~20% of the time)
    if (
        tier in (HandTier.PREMIUM, HandTier.STRONG)
        and position == Position.BLIND
        and not facing_raise
        and mix < 25
    ):
        # Limp with a monster from the blinds hoping someone raises
        return Decision("check", comment=f"[fox pre] {tag} limp-trap")

    # Standard action with opponent-adjusted ranges
    action = _fox_preflop_action(tier, position, facing_raise, opp_profiles, mix)

    if action == PreflopAction.FOLD:
        if amount_to_call == 0:
            return Decision("check", comment=f"[fox pre] {tag} check")
        return Decision("fold", comment=f"[fox pre] {tag} fold")

    if action == PreflopAction.CALL:
        if amount_to_call == 0:
            # In late position with playable hands, sometimes raise to isolate
            if tier in (HandTier.PLAYABLE, HandTier.STRONG) and position == Position.LATE:
                raise_to = max(min_raise, BIG_BLIND * 3)
                if raise_to < our_chips:
                    return Decision("bet", amount=raise_to, comment=f"[fox pre] {tag} iso")
            return Decision("check", comment=f"[fox pre] {tag} check")
        if amount_to_call >= our_chips:
            if tier in (HandTier.PREMIUM, HandTier.STRONG):
                return Decision("all_in", comment=f"[fox pre] {tag} all-in call")
            return Decision("fold", comment=f"[fox pre] {tag} too expensive")
        return Decision("call", comment=f"[fox pre] {tag} call")

    # RAISE -- deceptive sizing
    raise_to = _fox_preflop_raise_size(tier, position, min_raise, our_chips, mix)

    if raise_to >= our_chips:
        if tier == HandTier.PREMIUM:
            return Decision("all_in", comment=f"[fox pre] {tag} jam")
        if amount_to_call == 0:
            return Decision("check", comment=f"[fox pre] {tag} pot ctrl")
        return Decision("call", comment=f"[fox pre] {tag} call instead")

    if amount_to_call == 0:
        return Decision("bet", amount=raise_to, comment=f"[fox pre] {tag} open")
    return Decision("raise", amount=raise_to, comment=f"[fox pre] {tag} 3bet")


def _fox_preflop_action(
    tier: HandTier,
    position: Position,
    facing_raise: bool,
    opp_profiles: list[OpponentProfile],
    mix: int,
) -> PreflopAction:
    """Adjusted preflop action -- wider stealing range, trappier with premiums."""
    base = preflop_action(tier, position, facing_raise)

    # Against passive opponents, widen our stealing range significantly
    if all(p.is_passive for p in opp_profiles if p.hands_seen >= 5):
        if base == PreflopAction.CALL and tier == HandTier.PLAYABLE:
            return PreflopAction.RAISE
        if base == PreflopAction.FOLD and tier == HandTier.MARGINAL:
            if position in (Position.LATE, Position.MIDDLE):
                return PreflopAction.RAISE  # steal aggressively vs passive
            return PreflopAction.CALL

    # Against opponents who fold to raises a lot, bluff-raise more
    if any(p.fold_to_raise_pct > 0.55 and p.hands_seen >= 6 for p in opp_profiles):
        if base == PreflopAction.FOLD and tier == HandTier.MARGINAL:
            return PreflopAction.RAISE  # light 3-bet
        if base == PreflopAction.FOLD and tier == HandTier.TRASH and position == Position.LATE:
            if mix < 20:  # Occasionally steal with trash from the button
                return PreflopAction.RAISE

    # Against loose opponents, tighten up but value-raise more
    if any(p.is_loose for p in opp_profiles):
        if base == PreflopAction.CALL and tier == HandTier.MARGINAL:
            return PreflopAction.FOLD

    return base


def _fox_preflop_raise_size(
    tier: HandTier,
    position: Position,
    min_raise: int,
    our_chips: int,
    mix: int,
) -> int:
    """Deceptive preflop raise sizing -- varies to confuse opponents.

    Fox sometimes uses the same size for premiums and bluffs (balanced),
    and sometimes varies to exploit (small with premiums, big with bluffs).
    """
    # Balanced mode (~60%): same 2.5-3x size regardless of hand
    if mix < 60:
        base = max(int(BIG_BLIND * 2.7), min_raise)
        return base

    # Exploit mode (~40%): reverse sizing
    if tier == HandTier.PREMIUM:
        # Small raise with monsters to invite action
        base = max(int(BIG_BLIND * 2.2), min_raise)
    elif tier in (HandTier.STRONG, HandTier.PLAYABLE):
        base = max(BIG_BLIND * 3, min_raise)
    else:
        # Larger sizing with bluffs/steals to get folds
        base = max(int(BIG_BLIND * 3.5), min_raise)

    return base


# ---------------------------------------------------------------------------
#  Postflop
# ---------------------------------------------------------------------------

def _postflop(
    state: dict[str, Any],
    hole: tuple[str, ...],
    community: tuple[str, ...],
    pot: int,
    amount_to_call: int,
    min_raise: int,
    our_chips: int,
) -> Decision:
    """Postflop: deceptive play with slow-plays, check-raises, floats, probes."""
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
    spr = our_chips / max(pot, 1)
    mix = _mix(state)
    danger = _board_danger(board)

    # Hand strength qualifiers
    have_flush = has_flush((hole[0], hole[1]), community)
    have_flush_draw = has_flush_draw((hole[0], hole[1]), community)
    have_oesd = has_open_ended_straight_draw((hole[0], hole[1]), community)
    have_overpair = has_overpair((hole[0], hole[1]), community)
    have_top_pair = has_top_pair((hole[0], hole[1]), community)
    tp_kicker = top_pair_kicker_strength((hole[0], hole[1]), community)

    tag = f"eq={equity:.0%} d={danger:.1f} m={mix}"

    # ---- Monster hands (equity >= 80%) ----
    if equity >= 0.80:
        return _fox_play_monster(
            state, pot, min_raise, our_chips, amount_to_call,
            spr, opp_profiles, position, board, mix, tag,
        )

    # ---- Strong hands (equity >= 65%) ----
    if equity >= 0.65:
        return _fox_play_strong(
            state, pot, min_raise, our_chips, amount_to_call,
            spr, board, opp_profiles, position, mix, have_overpair,
            have_top_pair, tp_kicker, tag,
        )

    # ---- Drawing hands (flush draw or OESD) ----
    if (have_flush_draw or have_oesd) and equity >= 0.28:
        return _fox_play_draw(
            state, pot, min_raise, our_chips, amount_to_call,
            equity, pot_odds, opp_profiles, board, position, mix, tag,
        )

    # ---- Decent hands (equity >= 50%) ----
    if equity >= 0.50:
        return _fox_play_decent(
            state, pot, min_raise, our_chips, amount_to_call,
            board, opp_profiles, position, mix, tag,
        )

    # ---- Marginal but +EV call ----
    if equity >= pot_odds + 0.05 and amount_to_call > 0:
        if danger > 0.6 and any(p.is_aggressive for p in opp_profiles):
            if amount_to_call > pot * 0.5:
                return Decision("fold", comment=f"[fox] {tag} scary fold")
        if amount_to_call >= our_chips:
            if equity >= 0.40:
                return Decision("all_in", comment=f"[fox] {tag} committed")
            return Decision("fold", comment=f"[fox] {tag} not enough eq")
        return Decision("call", comment=f"[fox] {tag} +EV call")

    # ---- Float play (in position, called flop with nothing, now turn) ----
    float_dec = _consider_float(
        state, pot, min_raise, our_chips, amount_to_call,
        equity, board, opp_profiles, position, mix,
    )
    if float_dec is not None:
        return float_dec

    # ---- Probe bet (small bet on scare cards) ----
    probe_dec = _consider_probe(
        state, pot, min_raise, our_chips, amount_to_call,
        equity, board, opp_profiles, position, mix,
    )
    if probe_dec is not None:
        return probe_dec

    # ---- Bluff opportunities ----
    bluff = _fox_consider_bluff(
        state, pot, min_raise, our_chips, amount_to_call,
        equity, board, opp_profiles, position, mix,
    )
    if bluff is not None:
        return bluff

    # ---- Weak hand ----
    if amount_to_call == 0:
        return Decision("check", comment=f"[fox] {tag} weak check")
    return Decision("fold", comment=f"[fox] {tag} fold")


# ---------------------------------------------------------------------------
#  Monster play -- the heart of Fox's deception
# ---------------------------------------------------------------------------

def _fox_play_monster(
    state: dict[str, Any],
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    spr: float,
    opp_profiles: list[OpponentProfile],
    position: Position,
    board: BoardTexture,
    mix: int,
    tag: str,
) -> Decision:
    """Play a monster hand -- slow-play and trap most of the time."""
    # Low SPR: just jam, no room to maneuver
    if spr < 1.5:
        return Decision("all_in", comment=f"[fox monster] {tag} low-SPR jam")

    has_aggro_opponent = any(p.is_aggressive for p in opp_profiles)
    phase = state["phase"]

    # FACING A BET (amount_to_call > 0): check-raise or smooth call
    if amount_to_call > 0:
        # Check-raise: ~55% of the time, more vs aggressive opponents
        check_raise_threshold = 55 if has_aggro_opponent else 40
        if mix < check_raise_threshold and amount_to_call < our_chips:
            # Size the raise: small on dry boards (induce), big on wet (protect)
            if board.is_two_tone or board.has_straight_draw:
                raise_frac = 1.0  # pot-sized raise on wet boards
            else:
                raise_frac = 0.6  # smaller raise on dry boards to keep them in
            raise_to = max(min_raise, int(pot * raise_frac))
            if raise_to >= our_chips:
                return Decision("all_in", comment=f"[fox monster] {tag} c/r jam")
            if raise_to > amount_to_call:
                return Decision("raise", amount=raise_to, comment=f"[fox monster] {tag} c/r trap")

        # Smooth call to let them keep bluffing / building the pot
        if amount_to_call >= our_chips:
            return Decision("all_in", comment=f"[fox monster] {tag} snap call jam")
        return Decision("call", comment=f"[fox monster] {tag} smooth call")

    # NOT FACING A BET (amount_to_call == 0): slow-play vs bet for value

    # Against aggressive opponents: ALWAYS slow-play (let them hang themselves)
    if has_aggro_opponent and mix < 75:
        return Decision("check", comment=f"[fox monster] {tag} trap vs aggro")

    # On the flop: slow-play ~60% of the time
    if phase == "flop" and mix < 60:
        return Decision("check", comment=f"[fox monster] {tag} flop slowplay")

    # On the turn: slow-play ~40% (need to start building pot)
    if phase == "turn" and mix < 40:
        return Decision("check", comment=f"[fox monster] {tag} turn slowplay")

    # On the river: almost always bet (last chance for value), but use SMALL sizing
    # to induce a raise or a crying call
    if phase == "river":
        # Small bet to induce: ~50% of the time
        if mix < 50:
            target = max(min_raise, int(pot * 0.33))
        else:
            target = max(min_raise, int(pot * 0.70))
        if target >= our_chips:
            return Decision("all_in", comment=f"[fox monster] {tag} river jam")
        return Decision("bet", amount=target, comment=f"[fox monster] {tag} river value")

    # When we do bet: use reverse sizing (small bet to look weak)
    target = max(min_raise, int(pot * 0.35))
    if target >= our_chips:
        return Decision("all_in", comment=f"[fox monster] {tag} value jam")
    return Decision("bet", amount=target, comment=f"[fox monster] {tag} small value")


# ---------------------------------------------------------------------------
#  Strong play -- mix between value and deception
# ---------------------------------------------------------------------------

def _fox_play_strong(
    state: dict[str, Any],
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    spr: float,
    board: BoardTexture,
    opp_profiles: list[OpponentProfile],
    position: Position,
    mix: int,
    have_overpair: bool,
    have_top_pair: bool,
    tp_kicker: int,
    tag: str,
) -> Decision:
    """Play a strong hand -- mix between straightforward and tricky."""
    phase = state["phase"]
    has_aggro_opponent = any(p.is_aggressive for p in opp_profiles)

    # Low SPR: commit
    if spr < 2.5:
        if amount_to_call == 0:
            return Decision("all_in", comment=f"[fox strong] {tag} low-SPR jam")
        if amount_to_call >= our_chips:
            return Decision("all_in", comment=f"[fox strong] {tag} low-SPR call")
        raise_to = max(min_raise, int(pot * 0.8))
        if raise_to >= our_chips:
            return Decision("all_in", comment=f"[fox strong] {tag} jam")
        if raise_to > amount_to_call:
            return Decision("raise", amount=raise_to, comment=f"[fox strong] {tag} raise")
        return Decision("call", comment=f"[fox strong] {tag} call")

    # FACING A BET: check-raise or call depending on opponent and board
    if amount_to_call > 0:
        # Check-raise against aggressive opponents ~45% of the time
        if has_aggro_opponent and mix < 45 and amount_to_call < our_chips * 0.5:
            raise_to = max(min_raise, int(pot * 0.75))
            if raise_to >= our_chips:
                return Decision("all_in", comment=f"[fox strong] {tag} c/r jam")
            if raise_to > amount_to_call:
                return Decision("raise", amount=raise_to, comment=f"[fox strong] {tag} c/r")

        # On wet boards, raise to protect
        if (board.is_two_tone or board.has_straight_draw) and mix < 60:
            raise_to = max(min_raise, int(pot * 0.80))
            if raise_to >= our_chips:
                return Decision("all_in", comment=f"[fox strong] {tag} protect jam")
            if raise_to > amount_to_call:
                return Decision("raise", amount=raise_to, comment=f"[fox strong] {tag} protect raise")

        if amount_to_call >= our_chips:
            return Decision("all_in", comment=f"[fox strong] {tag} call jam")
        return Decision("call", comment=f"[fox strong] {tag} call")

    # NOT FACING A BET: decide between slow-play and value bet

    # Flop: slow-play with overpair on dry boards ~45% of the time
    if (
        phase == "flop"
        and have_overpair
        and board.is_rainbow
        and not board.has_straight_draw
        and mix < 45
    ):
        return Decision("check", comment=f"[fox strong] {tag} overpair trap")

    # Against aggressive opponents: check to induce bluff ~35%
    if has_aggro_opponent and mix < 35:
        return Decision("check", comment=f"[fox strong] {tag} check-induce")

    # Standard value bet with varied sizing
    if mix < 33:
        bet_frac = 0.35  # Small bet (looks weak, induces raises/calls)
    elif mix < 66:
        bet_frac = 0.55  # Standard
    else:
        bet_frac = 0.75  # Bigger on wet boards
        if board.is_rainbow and not board.has_straight_draw:
            bet_frac = 0.40  # But smaller on dry boards

    target = max(min_raise, int(pot * bet_frac))
    if target >= our_chips:
        return Decision("all_in", comment=f"[fox strong] {tag} value jam")
    return Decision("bet", amount=target, comment=f"[fox strong] {tag} value bet")


# ---------------------------------------------------------------------------
#  Draw play -- semi-bluffs and deceptive aggression
# ---------------------------------------------------------------------------

def _fox_play_draw(
    state: dict[str, Any],
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    equity: float,
    pot_odds: float,
    opp_profiles: list[OpponentProfile],
    board: BoardTexture,
    position: Position,
    mix: int,
    tag: str,
) -> Decision:
    """Play a draw with aggressive semi-bluffing and creative lines."""
    phase = state["phase"]

    # With check option: semi-bluff or check-raise
    if amount_to_call == 0:
        # On the flop: semi-bluff with large sizing ~65% of the time
        if phase == "flop":
            if mix < 65:
                # Overbet semi-bluff sometimes to apply maximum pressure
                if mix < 20:
                    bet_frac = 1.0  # pot-sized semi-bluff
                else:
                    bet_frac = 0.60
                target = max(min_raise, int(pot * bet_frac))
                if target >= our_chips:
                    if equity >= 0.42:
                        return Decision("all_in", comment=f"[fox draw] {tag} semi jam")
                    return Decision("check", comment=f"[fox draw] {tag} check")
                return Decision("bet", amount=target, comment=f"[fox draw] {tag} semi-bluff")
            # Check with plan to check-raise ~35%
            return Decision("check", comment=f"[fox draw] {tag} c/r setup")

        # On the turn: bet draws aggressively if flop checked through
        if phase == "turn":
            if _hand_state.get("flop_action") in ("check", None):
                # Delayed semi-bluff: bet the turn after checking flop
                target = max(min_raise, int(pot * 0.65))
                if target >= our_chips:
                    if equity >= 0.40:
                        return Decision("all_in", comment=f"[fox draw] {tag} delayed semi jam")
                    return Decision("check", comment=f"[fox draw] {tag} give up")
                return Decision("bet", amount=target, comment=f"[fox draw] {tag} delayed semi")
            # If we bet the flop, barrel the turn ~50%
            if mix < 50:
                target = max(min_raise, int(pot * 0.55))
                if target < our_chips:
                    return Decision("bet", amount=target, comment=f"[fox draw] {tag} barrel")
            return Decision("check", comment=f"[fox draw] {tag} pot ctrl draw")

        # River with a missed draw: give up or bluff
        # (Handled by bluff logic below)
        return Decision("check", comment=f"[fox draw] {tag} missed draw")

    # FACING A BET: call, raise as semi-bluff, or fold

    # Check-raise semi-bluff: ~35% of the time on flop if opponents fold often
    if (
        phase == "flop"
        and mix < 35
        and any(p.fold_to_raise_pct > 0.45 and p.hands_seen >= 5 for p in opp_profiles)
        and amount_to_call < our_chips * 0.3
    ):
        raise_to = max(min_raise, int(pot * 0.90))
        if raise_to < our_chips and raise_to > amount_to_call:
            return Decision("raise", amount=raise_to, comment=f"[fox draw] {tag} c/r semi")

    # Getting odds: call
    if equity >= pot_odds:
        if amount_to_call >= our_chips:
            if equity >= 0.38:
                return Decision("all_in", comment=f"[fox draw] {tag} draw jam call")
            return Decision("fold", comment=f"[fox draw] {tag} too much")
        return Decision("call", comment=f"[fox draw] {tag} draw call")

    # Not getting direct odds -- check implied odds
    if amount_to_call <= pot * 0.30 and equity >= 0.22:
        if amount_to_call >= our_chips:
            return Decision("fold", comment=f"[fox draw] {tag} implied fold")
        return Decision("call", comment=f"[fox draw] {tag} implied odds")

    return Decision("fold", comment=f"[fox draw] {tag} draw fold")


# ---------------------------------------------------------------------------
#  Decent hand play -- thin value and pot control
# ---------------------------------------------------------------------------

def _fox_play_decent(
    state: dict[str, Any],
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    board: BoardTexture,
    opp_profiles: list[OpponentProfile],
    position: Position,
    mix: int,
    tag: str,
) -> Decision:
    """Play a decent hand -- thin value bets with variable sizing."""
    phase = state["phase"]

    if amount_to_call == 0:
        # In position on dry boards: thin value bet ~55% of the time
        if not board.has_straight_draw and board.is_rainbow and position in (Position.LATE, Position.MIDDLE):
            if mix < 55:
                # Vary sizing: sometimes 30% (looks like probe), sometimes 55% (standard)
                bet_frac = 0.30 if mix < 25 else 0.50
                target = max(min_raise, int(pot * bet_frac))
                if target < our_chips:
                    return Decision("bet", amount=target, comment=f"[fox decent] {tag} thin value")

        # Out of position vs passive opponents: lead out ~30%
        if position in (Position.BLIND, Position.EARLY):
            if all(p.is_passive for p in opp_profiles if p.hands_seen >= 5) and mix < 30:
                target = max(min_raise, int(pot * 0.40))
                if target < our_chips:
                    return Decision("bet", amount=target, comment=f"[fox decent] {tag} lead")

        return Decision("check", comment=f"[fox decent] {tag} pot ctrl")

    # Facing a bet
    if amount_to_call >= our_chips:
        return Decision("fold", comment=f"[fox decent] {tag} too much")

    # Check-raise bluff with a decent hand ~15% of the time vs timid opponents
    if (
        mix < 15
        and any(p.fold_to_raise_pct > 0.55 and p.hands_seen >= 6 for p in opp_profiles)
        and amount_to_call < our_chips * 0.25
    ):
        raise_to = max(min_raise, int(pot * 0.75))
        if raise_to < our_chips and raise_to > amount_to_call:
            return Decision("raise", amount=raise_to, comment=f"[fox decent] {tag} c/r bluff")

    return Decision("call", comment=f"[fox decent] {tag} call")


# ---------------------------------------------------------------------------
#  Float play -- call flop in position, take pot on turn
# ---------------------------------------------------------------------------

def _consider_float(
    state: dict[str, Any],
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    equity: float,
    board: BoardTexture,
    opp_profiles: list[OpponentProfile],
    position: Position,
    mix: int,
) -> Decision | None:
    """Float play: call with nothing on the flop in position, stab the turn.

    Requirements:
    - We are in position (late)
    - On the flop, facing a small-to-medium bet
    - On the turn, opponent checks to us (we take it)
    """
    phase = state["phase"]

    # FLOP: set up the float (call a small bet in position with weak hand)
    if (
        phase == "flop"
        and position == Position.LATE
        and amount_to_call > 0
        and amount_to_call <= pot * 0.55  # only float against smaller bets
        and equity >= 0.15  # need some equity (backdoors count)
        and equity < 0.50   # not a real hand (would play normally)
        and mix < 35        # float ~35% of these spots
        and amount_to_call < our_chips
    ):
        return Decision("call", comment=f"[fox float] eq={equity:.0%} flop call")

    # TURN: complete the float (bet when checked to after floating the flop)
    if (
        phase == "turn"
        and position == Position.LATE
        and amount_to_call == 0
        and _hand_state.get("flop_action") == "call"
        and equity < 0.45  # still weak -- this is a bluff
        and mix < 65       # follow through ~65% of the time (committed to the line)
    ):
        # Size it like a real bet: 55-70% pot
        bet_frac = 0.55 if mix < 30 else 0.70
        target = max(min_raise, int(pot * bet_frac))
        if target < our_chips * 0.35:  # don't risk too much on a float
            return Decision("bet", amount=target, comment=f"[fox float] turn stab")

    return None


# ---------------------------------------------------------------------------
#  Probe bet -- small bet on scare cards to steal
# ---------------------------------------------------------------------------

def _consider_probe(
    state: dict[str, Any],
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    equity: float,
    board: BoardTexture,
    opp_profiles: list[OpponentProfile],
    position: Position,
    mix: int,
) -> Decision | None:
    """Probe bet: small bet on scary board cards to take down the pot.

    Effective when:
    - Turn or river brings a scare card (broadway, completing a draw)
    - Opponents have checked showing weakness
    - We have initiative from position
    """
    phase = state["phase"]

    if amount_to_call > 0:
        return None  # can't probe when facing a bet

    if phase not in ("turn", "river"):
        return None

    # Only probe from position or when we were the previous-street aggressor
    if position not in (Position.LATE, Position.MIDDLE):
        return None

    # Board must be at least somewhat scary
    if not (board.is_two_tone or board.has_straight_draw or board.num_broadway >= 3 or board.is_paired):
        return None

    # Don't probe with real hands (handled by other logic)
    if equity >= 0.45:
        return None

    # Probe ~40% of eligible spots
    if mix >= 40:
        return None

    # Small bet: 25-35% pot (looks like a blocking bet or thin value)
    bet_frac = 0.25 if mix < 20 else 0.33
    target = max(min_raise, int(pot * bet_frac))

    if target >= our_chips * 0.20:
        return None  # don't risk too much on a probe

    return Decision("bet", amount=target, comment=f"[fox probe] {phase} probe")


# ---------------------------------------------------------------------------
#  Bluff logic -- overbet bluffs, river bluffs, continuation bets
# ---------------------------------------------------------------------------

def _fox_consider_bluff(
    state: dict[str, Any],
    pot: int,
    min_raise: int,
    our_chips: int,
    amount_to_call: int,
    equity: float,
    board: BoardTexture,
    opp_profiles: list[OpponentProfile],
    position: Position,
    mix: int,
) -> Decision | None:
    """Fox bluff logic: varied sizing, overbets, well-timed aggression."""
    if amount_to_call > 0:
        return None  # don't bluff into bets (unless it's a raise-bluff, handled elsewhere)

    active = _count_active_opponents(state)
    if active > 2:
        return None  # don't bluff multiway

    phase = state["phase"]
    fold_happy = any(
        p.fold_to_raise_pct > 0.45 and p.hands_seen >= 5
        for p in opp_profiles
    )
    all_passive = all(p.is_passive for p in opp_profiles if p.hands_seen >= 5) and len(opp_profiles) > 0

    # --- C-bet on flop (preflop raiser) ---
    if phase == "flop" and _hand_state.get("was_preflop_raiser"):
        # C-bet ~70% of the time on favorable boards
        if board.high_card_rank >= 8 and mix < 70:
            # Vary c-bet sizing: small on dry, big on wet
            if board.is_rainbow and not board.has_straight_draw:
                bet_frac = 0.33  # small c-bet on dry boards
            else:
                bet_frac = 0.55
            target = max(min_raise, int(pot * bet_frac))
            if target < our_chips * 0.25:
                return Decision("bet", amount=target, comment=f"[fox bluff] cbet")
        # C-bet on low boards too, but less often (~40%)
        elif mix < 40:
            target = max(min_raise, int(pot * 0.40))
            if target < our_chips * 0.20:
                return Decision("bet", amount=target, comment=f"[fox bluff] low cbet")

    # --- Turn barrel after c-betting ---
    if (
        phase == "turn"
        and _hand_state.get("flop_action") in ("bet",)
        and (fold_happy or all_passive)
        and mix < 45
    ):
        target = max(min_raise, int(pot * 0.55))
        if target < our_chips * 0.30:
            return Decision("bet", amount=target, comment=f"[fox bluff] turn barrel")

    # --- River bluff: represent the completed draw ---
    if phase == "river":
        # On boards where draws completed, bluff with a big sizing
        if (board.is_two_tone or board.has_straight_draw) and mix < 35:
            # Overbet bluff ~15% of the time (looks like a huge hand)
            if mix < 15:
                bet_frac = 1.20  # overbet
            else:
                bet_frac = 0.70
            target = max(min_raise, int(pot * bet_frac))
            if target < our_chips * 0.35:
                return Decision("bet", amount=target, comment=f"[fox bluff] river rep")

        # On paired boards, represent the trips/full house ~25%
        if board.is_paired and mix < 25 and fold_happy:
            target = max(min_raise, int(pot * 0.65))
            if target < our_chips * 0.30:
                return Decision("bet", amount=target, comment=f"[fox bluff] rep trips")

    # --- Steal when everyone shows weakness (position required) ---
    if position == Position.LATE and mix < 30:
        if all_passive or fold_happy:
            target = max(min_raise, int(pot * 0.45))
            if target < our_chips * 0.20:
                return Decision("bet", amount=target, comment=f"[fox bluff] steal")

    return None


# ---------------------------------------------------------------------------
#  Helpers (shared with other strategies)
# ---------------------------------------------------------------------------

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
