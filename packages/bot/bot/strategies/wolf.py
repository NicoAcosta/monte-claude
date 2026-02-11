"""Wolf strategy: Hyper-aggressive LAG (Loose-Aggressive) poker bot.

Wolf is built to dominate 4-player tournaments through relentless pressure:
- Opens 40-50% of hands from late position with custom wide ranges
- Aggressive 3-betting and 4-betting with polarized ranges
- ~75% continuation bet frequency on flop, high double/triple barrel rates
- Larger bet sizing to maximize fold equity
- Momentum tracking: the preflop aggressor keeps firing
- Gear-shifting: tightens up against calling stations, attacks folders
- Position-obsessed: plays very differently IP vs OOP
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..cards import gap, is_pair, is_suited, rank_index
from ..equity import estimate_equity
from ..preflop_ranges import (
    HandTier,
    Position,
    classify_hand,
    determine_position,
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

# ---------------------------------------------------------------------------
# Global state that persists across calls within one game session
# ---------------------------------------------------------------------------
_tracker = OpponentTracker()

# Momentum tracking: did WE raise preflop this hand?
_preflop_aggressor: bool = False
_last_hand_number: int = -1

# Gear state: when opponents start calling too much, shift down
_gear: int = 2  # 0=low (tight/value), 1=medium (balanced), 2=high (hyper-aggro)
_hands_played: int = 0
_bluffs_caught: int = 0  # times we bet and got called/raised with weak equity


@dataclass(frozen=True)
class Decision:
    action: str
    amount: int | None = None
    comment: str | None = None


# ===================================================================
# Public API
# ===================================================================


def decide(state: dict[str, Any]) -> Decision:
    """Main entry point: state dict -> Decision."""
    global _preflop_aggressor, _last_hand_number, _hands_played

    _tracker.update(state)

    hand_number = state.get("hand_number", 0)
    if hand_number != _last_hand_number:
        _preflop_aggressor = False
        _last_hand_number = hand_number
        _hands_played += 1
        _maybe_shift_gears()

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
    """Reset all global state for a new game."""
    global _tracker, _preflop_aggressor, _last_hand_number
    global _gear, _hands_played, _bluffs_caught
    _tracker = OpponentTracker()
    _preflop_aggressor = False
    _last_hand_number = -1
    _gear = 2
    _hands_played = 0
    _bluffs_caught = 0


# ===================================================================
# Gear Shifting
# ===================================================================

def _maybe_shift_gears() -> None:
    """Adjust aggression gear based on how opponents are responding."""
    global _gear, _bluffs_caught

    if _hands_played < 8:
        return  # Not enough data

    # If we are getting called/raised a lot, shift down
    bluff_rate = _bluffs_caught / max(_hands_played, 1)
    if bluff_rate > 0.35:
        _gear = 0  # Opponents are calling stations -- value only
    elif bluff_rate > 0.20:
        _gear = 1  # Medium aggression
    else:
        _gear = 2  # Full wolf mode


def _aggression_multiplier() -> float:
    """How aggressive should we be? Returns 0.6-1.0 based on gear."""
    if _gear == 0:
        return 0.6
    if _gear == 1:
        return 0.8
    return 1.0


# ===================================================================
# Wolf's Custom Preflop Ranges (much wider than standard)
# ===================================================================

def _wolf_hand_playability(a: str, b: str) -> float:
    """Score a starting hand 0.0 to 1.0 for Wolf's opening range.

    Wolf's range is much wider than the standard chart. Returns a
    continuous score so we can make nuanced decisions.
    """
    hi = max(rank_index(a), rank_index(b))
    lo = min(rank_index(a), rank_index(b))
    suited = is_suited(a, b)
    pair = is_pair(a, b)
    g = gap(a, b)

    # Pocket pairs: always playable, value scales with rank
    if pair:
        return 0.55 + (hi / 12.0) * 0.45  # 22=0.55, AA=1.0

    # Suited hands get a big boost
    suit_bonus = 0.12 if suited else 0.0

    # High card value
    high_val = hi / 12.0  # 0.0 for 2, 1.0 for A
    low_val = lo / 12.0

    # Connectedness bonus (suited connectors are gold for LAG)
    connect_bonus = 0.0
    if g == 0:
        connect_bonus = 0.10
    elif g == 1:
        connect_bonus = 0.05

    # Broadway combos
    broadway_bonus = 0.08 if hi >= 8 and lo >= 8 else 0.0

    # Ace-x hands (suited aces are great bluff candidates)
    ace_bonus = 0.0
    if hi == 12:
        ace_bonus = 0.10 if suited else 0.04

    score = (high_val * 0.35 + low_val * 0.20 + suit_bonus +
             connect_bonus + broadway_bonus + ace_bonus)
    return min(score, 1.0)


def _should_open(hole: tuple[str, ...], position: Position) -> str:
    """Wolf's custom opening decision. Returns 'raise', 'call', or 'fold'.

    Wolf opens MUCH wider than standard, especially in late position.
    """
    score = _wolf_hand_playability(hole[0], hole[1])
    tier = classify_hand(hole[0], hole[1])
    mult = _aggression_multiplier()

    # Premium hands always raise
    if tier == HandTier.PREMIUM:
        return "raise"

    # Position-based thresholds (lower = wider range)
    thresholds = {
        Position.LATE:   {"raise": 0.35 * mult, "call": 0.25 * mult},
        Position.MIDDLE: {"raise": 0.42 * mult, "call": 0.32 * mult},
        Position.EARLY:  {"raise": 0.50 * mult, "call": 0.40 * mult},
        Position.BLIND:  {"raise": 0.45 * mult, "call": 0.28 * mult},
    }

    t = thresholds.get(position, thresholds[Position.MIDDLE])

    if score >= t["raise"]:
        return "raise"
    if score >= t["call"]:
        return "call"
    return "fold"


def _should_defend_vs_raise(
    hole: tuple[str, ...],
    position: Position,
    raise_size_bb: float,
    opp_profiles: list[OpponentProfile],
) -> str:
    """Facing a raise: 3bet, call, or fold. Wolf 3-bets with polarized range."""
    score = _wolf_hand_playability(hole[0], hole[1])
    tier = classify_hand(hole[0], hole[1])
    mult = _aggression_multiplier()

    # Premium: always 3-bet (or 4-bet)
    if tier == HandTier.PREMIUM:
        return "raise"

    # Strong: 3-bet for value
    if tier == HandTier.STRONG:
        return "raise"

    # Against opponents who fold a lot to 3-bets, widen our 3-bet bluff range
    high_fold_opponents = any(
        p.fold_to_raise_pct > 0.55 and p.hands_seen >= 5
        for p in opp_profiles
    )

    if high_fold_opponents and mult >= 0.8:
        # 3-bet bluff with suited connectors, suited aces, and decent hands
        if score >= 0.35 and (is_suited(hole[0], hole[1]) or tier == HandTier.PLAYABLE):
            return "raise"

    # Call range (wider in position)
    if position in (Position.LATE, Position.BLIND):
        call_threshold = 0.30 * mult
    else:
        call_threshold = 0.40 * mult

    # Tighten against large raises
    if raise_size_bb > 8:
        call_threshold += 0.10
    if raise_size_bb > 15:
        call_threshold += 0.10

    if score >= call_threshold:
        if tier in (HandTier.PLAYABLE, HandTier.MARGINAL):
            return "call"
        if tier == HandTier.STRONG:
            return "raise"

    return "fold"


# ===================================================================
# Preflop
# ===================================================================

def _preflop(
    state: dict[str, Any],
    hole: tuple[str, ...],
    amount_to_call: int,
    min_raise: int,
    our_chips: int,
    pot: int,
) -> Decision:
    """Wolf's preflop decision: wide opens, polarized 3-bets, big sizing."""
    global _preflop_aggressor

    position = _get_position(state)
    tier = classify_hand(hole[0], hole[1])
    score = _wolf_hand_playability(hole[0], hole[1])
    opp_profiles = _get_opponent_profiles(state)
    facing_raise = amount_to_call > BIG_BLIND
    tag = f"wolf/{tier.value}/{position.value}"

    if facing_raise:
        raise_size_bb = amount_to_call / BIG_BLIND
        action = _should_defend_vs_raise(hole, position, raise_size_bb, opp_profiles)
    else:
        action = _should_open(hole, position)

    # --- FOLD ---
    if action == "fold":
        if amount_to_call == 0:
            return Decision("check", comment=f"[pre] {tag} check")
        return Decision("fold", comment=f"[pre] {tag} fold")

    # --- CALL ---
    if action == "call":
        if amount_to_call == 0:
            # With decent+ hands in position, raise instead of limping
            # Wolf NEVER limps -- raise or fold
            if score >= 0.30 and position in (Position.LATE, Position.MIDDLE):
                raise_to = _wolf_preflop_sizing(position, min_raise, our_chips, pot, opp_profiles)
                if raise_to < our_chips:
                    _preflop_aggressor = True
                    return Decision("bet", amount=raise_to, comment=f"[pre] {tag} no-limp raise")
            return Decision("check", comment=f"[pre] {tag} check")
        if amount_to_call >= our_chips:
            if tier in (HandTier.PREMIUM, HandTier.STRONG):
                _preflop_aggressor = True
                return Decision("all_in", comment=f"[pre] {tag} all-in call")
            return Decision("fold", comment=f"[pre] {tag} too expensive")
        return Decision("call", comment=f"[pre] {tag} call")

    # --- RAISE ---
    _preflop_aggressor = True

    # Size the raise -- Wolf sizes BIG
    raise_to = _wolf_preflop_sizing(position, min_raise, our_chips, pot, opp_profiles)

    if raise_to >= our_chips:
        if tier in (HandTier.PREMIUM, HandTier.STRONG):
            return Decision("all_in", comment=f"[pre] {tag} jam")
        # Don't shove marginal -- downsize
        if amount_to_call == 0:
            smaller = max(min_raise, int(BIG_BLIND * 2.5))
            if smaller < our_chips:
                return Decision("bet", amount=smaller, comment=f"[pre] {tag} small open")
            return Decision("check", comment=f"[pre] {tag} pot control")
        return Decision("call", comment=f"[pre] {tag} call instead")

    if amount_to_call == 0:
        return Decision("bet", amount=raise_to, comment=f"[pre] {tag} open")

    # 3-bet or 4-bet
    return Decision("raise", amount=raise_to, comment=f"[pre] {tag} 3bet")


def _wolf_preflop_sizing(
    position: Position,
    min_raise: int,
    our_chips: int,
    pot: int,
    opp_profiles: list[OpponentProfile],
) -> int:
    """Wolf sizes preflop raises BIGGER than standard to maximize fold equity."""
    # Base sizing: 3.5x BB (bigger than shark's 3x)
    base = int(BIG_BLIND * 3.5)

    # Late position can open slightly smaller to risk less with wide range
    if position == Position.LATE:
        base = max(int(BIG_BLIND * 2.8), min_raise)
    elif position == Position.EARLY:
        base = max(int(BIG_BLIND * 3.5), min_raise)
    elif position == Position.BLIND:
        # Blind 3-bets: size to 4x
        base = max(BIG_BLIND * 4, min_raise)

    # Against loose/calling opponents, size UP even more
    has_loose = any(p.is_loose for p in opp_profiles)
    has_passive = any(p.is_passive and p.hands_seen >= 5 for p in opp_profiles)

    if has_loose:
        base = max(base, int(BIG_BLIND * 4))
    if has_passive:
        # Passive opponents call too much: size up for value, down for bluffs
        # But Wolf defaults to sizing up because it has range advantage
        base = max(base, int(BIG_BLIND * 3.5))

    # If there is already money in the pot (3-bet situation), size 3x the raise
    if pot > BIG_BLIND * 3:
        base = max(base, int(pot * 0.9))

    return max(base, min_raise)


# ===================================================================
# Postflop
# ===================================================================

def _postflop(
    state: dict[str, Any],
    hole: tuple[str, ...],
    community: tuple[str, ...],
    pot: int,
    amount_to_call: int,
    min_raise: int,
    our_chips: int,
) -> Decision:
    """Wolf's postflop: momentum-driven, barrel-happy, position-obsessed."""
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
    phase = state["phase"]
    mult = _aggression_multiplier()

    # Hand strength qualifiers
    have_flush = has_flush((hole[0], hole[1]), community)
    have_flush_draw = has_flush_draw((hole[0], hole[1]), community)
    have_oesd = has_open_ended_straight_draw((hole[0], hole[1]), community)
    have_overpair = has_overpair((hole[0], hole[1]), community)
    have_top_pair = has_top_pair((hole[0], hole[1]), community)
    tp_kicker = top_pair_kicker_strength((hole[0], hole[1]), community)

    danger = _board_danger(board)
    tag = f"eq={equity:.0%} po={pot_odds:.0%} d={danger:.1f} g={_gear}"

    # =============================================================
    # Monster hands (equity >= 75%) -- Wolf sets traps or goes big
    # =============================================================
    if equity >= 0.75:
        return _wolf_play_monster(
            pot, min_raise, our_chips, amount_to_call, spr,
            opp_profiles, position, board, tag,
        )

    # =============================================================
    # Strong hands (equity >= 60%) -- Bet for value and protection
    # =============================================================
    if equity >= 0.60:
        return _wolf_play_strong(
            pot, min_raise, our_chips, amount_to_call, spr,
            board, opp_profiles, position, phase, tag,
        )

    # =============================================================
    # Drawing hands with decent equity -- Semi-bluff aggressively
    # =============================================================
    if (have_flush_draw or have_oesd) and equity >= 0.25:
        return _wolf_play_draw(
            pot, min_raise, our_chips, amount_to_call,
            equity, pot_odds, opp_profiles, board, position, phase, tag,
        )

    # =============================================================
    # Medium hands (equity >= 45%) -- Bet in position, pot control OOP
    # =============================================================
    if equity >= 0.45:
        return _wolf_play_medium(
            pot, min_raise, our_chips, amount_to_call,
            board, opp_profiles, position, equity, phase, tag,
            have_flush=have_flush,
        )

    # =============================================================
    # Marginal +EV calls
    # =============================================================
    if equity >= pot_odds + 0.05 and amount_to_call > 0:
        if danger > 0.6 and any(p.is_aggressive for p in opp_profiles):
            if amount_to_call > pot * 0.5:
                return Decision("fold", comment=f"[post] {tag} scary board fold")
        if amount_to_call >= our_chips:
            if equity >= 0.38:
                return Decision("all_in", comment=f"[post] {tag} committed")
            return Decision("fold", comment=f"[post] {tag} not enough eq")
        return Decision("call", comment=f"[post] {tag} +EV call")

    # =============================================================
    # Bluff / Continuation bet / Barrel
    # =============================================================
    bluff = _wolf_consider_bluff(
        state, pot, min_raise, our_chips, amount_to_call,
        equity, board, opp_profiles, position, phase,
        have_flush_draw, have_oesd, have_top_pair, have_overpair,
    )
    if bluff is not None:
        return bluff

    # =============================================================
    # Give up
    # =============================================================
    if amount_to_call == 0:
        return Decision("check", comment=f"[post] {tag} weak check")
    return Decision("fold", comment=f"[post] {tag} fold")


# -------------------------------------------------------------------
# Postflop hand categories
# -------------------------------------------------------------------

def _wolf_play_monster(
    pot: int, min_raise: int, our_chips: int, amount_to_call: int,
    spr: float, opp_profiles: list[OpponentProfile],
    position: Position, board: BoardTexture, tag: str,
) -> Decision:
    """Play a monster hand -- max extraction. Wolf sizes BIG."""
    # Low SPR: just jam
    if spr < 2.5:
        return Decision("all_in", comment=f"[post] {tag} low-SPR jam")

    # Against passive opponents who call too much: overbet for value
    has_callers = any(
        p.is_passive or (p.aggression_factor < 1.5 and p.hands_seen >= 5)
        for p in opp_profiles
    )

    if has_callers:
        bet_frac = 0.90  # Overbet into calling stations
    elif any(p.is_aggressive for p in opp_profiles):
        # Against aggressive opponents: let them bet into us sometimes
        if amount_to_call > 0 and position == Position.LATE:
            # Flat call to let them keep bluffing, then raise river
            if board.num_community < 5:
                return Decision("call", comment=f"[post] {tag} monster trap call")
        bet_frac = 0.75
    else:
        bet_frac = 0.80

    target = max(min_raise, int(pot * bet_frac))
    if target >= our_chips:
        return Decision("all_in", comment=f"[post] {tag} value jam")

    if amount_to_call == 0:
        return Decision("bet", amount=target, comment=f"[post] {tag} value bet")
    if target <= amount_to_call:
        # We wanted to bet less than what we need to call. Just call (slowplay).
        if amount_to_call >= our_chips:
            return Decision("all_in", comment=f"[post] {tag} monster all-in call")
        return Decision("call", comment=f"[post] {tag} monster call")
    return Decision("raise", amount=target, comment=f"[post] {tag} value raise")


def _wolf_play_strong(
    pot: int, min_raise: int, our_chips: int, amount_to_call: int,
    spr: float, board: BoardTexture, opp_profiles: list[OpponentProfile],
    position: Position, phase: str, tag: str,
) -> Decision:
    """Strong hand -- Wolf bets bigger than Shark for protection + value."""
    # On wet boards, bet large to deny draws
    if board.has_straight_draw or board.is_two_tone or board.is_monotone:
        bet_frac = 0.80  # Shark does 0.75; Wolf sizes up
    else:
        bet_frac = 0.65  # Shark does 0.55; Wolf still bets big on dry

    # Wolf does NOT slow-play strong hands. Shark traps on dry flops;
    # Wolf keeps betting because aggression prints money.
    target = max(min_raise, int(pot * bet_frac))

    # Low SPR with strong hand: just commit
    if spr < 3.0 and target >= our_chips * 0.6:
        return Decision("all_in", comment=f"[post] {tag} strong commit jam")

    if target >= our_chips:
        return Decision("all_in", comment=f"[post] {tag} strong jam")

    if amount_to_call == 0:
        return Decision("bet", amount=target, comment=f"[post] {tag} strong bet")
    if target <= amount_to_call:
        if amount_to_call >= our_chips:
            return Decision("all_in", comment=f"[post] {tag} strong all-in call")
        return Decision("call", comment=f"[post] {tag} strong call")
    return Decision("raise", amount=target, comment=f"[post] {tag} strong raise")


def _wolf_play_draw(
    pot: int, min_raise: int, our_chips: int, amount_to_call: int,
    equity: float, pot_odds: float, opp_profiles: list[OpponentProfile],
    board: BoardTexture, position: Position, phase: str, tag: str,
) -> Decision:
    """Drawing hand -- Wolf semi-bluffs HARD. Bets bigger than Shark."""
    mult = _aggression_multiplier()

    # Wolf's semi-bluffs are large to maximize fold equity
    if amount_to_call == 0:
        # Bet 70-75% pot as semi-bluff (Shark does 60%)
        bet_frac = 0.70 * mult + 0.05
        target = max(min_raise, int(pot * bet_frac))

        if target >= our_chips:
            # Wolf jams draws more aggressively than Shark
            if equity >= 0.38:
                return Decision("all_in", comment=f"[post] {tag} draw jam")
            return Decision("check", comment=f"[post] {tag} draw check")
        return Decision("bet", amount=target, comment=f"[post] {tag} semi-bluff")

    # Facing a bet with a draw
    if equity >= pot_odds:
        # Check-raise semi-bluff: Wolf does this MORE often than Shark
        fold_happy = any(
            p.fold_to_raise_pct > 0.45 and p.hands_seen >= 4
            for p in opp_profiles
        )

        if fold_happy and amount_to_call < our_chips * 0.35 and mult >= 0.8:
            raise_to = max(min_raise, int(pot * 0.90))
            if raise_to < our_chips:
                return Decision("raise", amount=raise_to, comment=f"[post] {tag} draw c/r bluff")

        # In position: sometimes flat-call to realize equity cheaply
        if position == Position.LATE:
            if amount_to_call >= our_chips:
                if equity >= 0.38:
                    return Decision("all_in", comment=f"[post] {tag} draw all-in")
                return Decision("fold", comment=f"[post] {tag} draw too much")
            return Decision("call", comment=f"[post] {tag} draw IP call")

        # OOP with odds: call
        if amount_to_call >= our_chips:
            if equity >= 0.38:
                return Decision("all_in", comment=f"[post] {tag} draw all-in")
            return Decision("fold", comment=f"[post] {tag} draw too much")
        return Decision("call", comment=f"[post] {tag} draw call")

    # Not getting direct odds
    # Wolf still calls small bets with implied odds more liberally
    if amount_to_call <= pot * 0.30 and equity >= 0.22:
        if amount_to_call >= our_chips:
            return Decision("fold", comment=f"[post] {tag} draw fold")
        return Decision("call", comment=f"[post] {tag} implied odds call")

    # Aggressive: sometimes raise even without odds vs weak opponents
    if (
        mult >= 0.8
        and any(p.fold_to_raise_pct > 0.55 and p.hands_seen >= 5 for p in opp_profiles)
        and amount_to_call < our_chips * 0.25
    ):
        raise_to = max(min_raise, int(pot * 0.85))
        if raise_to < our_chips:
            return Decision("raise", amount=raise_to, comment=f"[post] {tag} draw bluff raise")

    return Decision("fold", comment=f"[post] {tag} draw fold")


def _wolf_play_medium(
    pot: int, min_raise: int, our_chips: int, amount_to_call: int,
    board: BoardTexture, opp_profiles: list[OpponentProfile],
    position: Position, equity: float, phase: str, tag: str,
    *, have_flush: bool = False,
) -> Decision:
    """Medium hand: Wolf bets in position, controls pot OOP.

    This is where Wolf diverges most from Shark. Shark plays passively
    with medium hands. Wolf turns them into betting hands in position.
    """
    mult = _aggression_multiplier()

    if amount_to_call == 0:
        # IN POSITION: bet for thin value and to deny equity
        if position in (Position.LATE, Position.MIDDLE):
            # Wolf bets medium hands on almost all textures in position
            if board.is_monotone and not have_flush:
                # Exception: monotone board and we don't have the flush
                return Decision("check", comment=f"[post] {tag} medium mono check")
            bet_frac = 0.50 * mult + 0.05
            target = max(min_raise, int(pot * bet_frac))
            if target < our_chips:
                return Decision("bet", amount=target, comment=f"[post] {tag} medium thin value")
            return Decision("check", comment=f"[post] {tag} medium check")
        # OOP: check to control pot (even Wolf respects OOP with medium hands)
        return Decision("check", comment=f"[post] {tag} medium pot control")

    # Facing a bet with medium hand
    if amount_to_call >= our_chips:
        if equity >= 0.48:
            return Decision("all_in", comment=f"[post] {tag} medium committed")
        return Decision("fold", comment=f"[post] {tag} medium fold to jam")

    # In position: call more liberally (we close the action)
    if position == Position.LATE:
        if amount_to_call <= pot * 0.60:
            return Decision("call", comment=f"[post] {tag} medium IP call")
    else:
        if amount_to_call <= pot * 0.40:
            return Decision("call", comment=f"[post] {tag} medium OOP call")

    return Decision("fold", comment=f"[post] {tag} medium fold")


# -------------------------------------------------------------------
# The Heart of Wolf: Bluffing Engine
# -------------------------------------------------------------------

def _wolf_consider_bluff(
    state: dict[str, Any],
    pot: int, min_raise: int, our_chips: int, amount_to_call: int,
    equity: float, board: BoardTexture, opp_profiles: list[OpponentProfile],
    position: Position, phase: str,
    have_flush_draw: bool, have_oesd: bool,
    have_top_pair: bool, have_overpair: bool,
) -> Decision | None:
    """Wolf's bluffing engine -- this is where the magic happens.

    Key principles:
    1. MOMENTUM: If we were the preflop aggressor, c-bet ~75% of flops
    2. DOUBLE BARREL: Continue on the turn if the board favors us
    3. TRIPLE BARREL: Fire river bluffs on scare cards
    4. POSITION: Only bluff in position or as the aggressor
    5. OPPONENT READS: Don't bluff calling stations
    """
    mult = _aggression_multiplier()
    active = _count_active_opponents(state)

    # Don't bluff into 3+ opponents (multi-way = someone has it)
    if active > 2:
        return None

    # ---- Identify if opponents are calling stations ----
    any_calling_station = any(
        (p.is_passive or p.is_loose) and p.fold_to_raise_pct < 0.35 and p.hands_seen >= 6
        for p in opp_profiles
    )
    if any_calling_station and _gear <= 1:
        # Against calling stations in lower gears: don't bluff
        return None

    # ---- How likely are opponents to fold? ----
    avg_fold_pct = 0.5  # default assumption
    fold_data_opps = [p for p in opp_profiles if p.hands_seen >= 4]
    if fold_data_opps:
        avg_fold_pct = sum(p.fold_to_raise_pct for p in fold_data_opps) / len(fold_data_opps)

    # ================================================================
    # C-BET: Flop continuation bet (we were the preflop aggressor)
    # ================================================================
    if board.num_community == 3 and _preflop_aggressor and amount_to_call == 0:
        # Wolf c-bets ~75% of flops. Only check back on the worst textures.
        skip_cbet = (
            (board.is_monotone and not have_flush_draw)
            or (board.is_connected and board.has_straight_draw and board.num_broadway == 0)
        )

        if not skip_cbet and mult >= 0.6:
            # Size: 50-66% pot depending on board texture
            if board.is_rainbow and not board.has_straight_draw:
                # Dry board: smaller c-bet (we c-bet wider so risk less)
                cbet_frac = 0.45
            elif board.high_card_rank >= 8:
                # High board (favors preflop raiser's range): bigger
                cbet_frac = 0.60
            else:
                cbet_frac = 0.55

            cbet_frac *= mult
            target = max(min_raise, int(pot * cbet_frac))
            if target < our_chips:
                return Decision("bet", amount=target, comment=f"[bluff] wolf cbet")
            return None

    # ================================================================
    # DOUBLE BARREL: Turn continuation bet
    # ================================================================
    if board.num_community == 4 and _preflop_aggressor and amount_to_call == 0:
        # Wolf barrels the turn when:
        # - Board texture is good (high cards, scare cards)
        # - We have some equity (backdoor draws, overcards)
        # - Opponents are likely to fold

        should_barrel = False
        barrel_frac = 0.55

        # Scare card turns (A, K, Q) favor the aggressor
        if board.high_card_rank >= 10:
            should_barrel = True
            barrel_frac = 0.60

        # Two-tone board: represent the draw getting there
        if board.is_two_tone:
            should_barrel = True
            barrel_frac = 0.55

        # We have some equity (any draw or overcards)
        if equity >= 0.20 and (have_flush_draw or have_oesd):
            should_barrel = True
            barrel_frac = 0.65

        # Paired board: less likely opponent connected
        if board.is_paired:
            should_barrel = True
            barrel_frac = 0.50

        # Opponents fold enough to make it profitable
        if avg_fold_pct >= 0.40 and should_barrel and mult >= 0.8:
            target = max(min_raise, int(pot * barrel_frac * mult))
            if target < our_chips * 0.5:  # Don't risk half our stack on a barrel
                return Decision("bet", amount=target, comment=f"[bluff] wolf double barrel")

    # ================================================================
    # TRIPLE BARREL: River bluff
    # ================================================================
    if board.num_community == 5 and amount_to_call == 0:
        should_river_bluff = False
        river_frac = 0.65

        # Represent completed draws
        if board.is_monotone or (board.is_two_tone and board.num_community == 5):
            should_river_bluff = True
            river_frac = 0.70

        # Represent the straight
        if board.has_straight_draw and board.is_connected:
            should_river_bluff = True
            river_frac = 0.65

        # Scare card river: high card on board
        if board.high_card_rank >= 10 and board.num_broadway >= 3:
            should_river_bluff = True
            river_frac = 0.60

        # Paired board: represent trips/full house
        if board.is_paired or board.is_double_paired:
            should_river_bluff = True
            river_frac = 0.55

        # Only bluff if opponents are folding enough and we're in high gear
        if should_river_bluff and avg_fold_pct >= 0.45 and mult >= 0.8:
            # Only bluff in position or as PFR
            if position in (Position.LATE, Position.MIDDLE) or _preflop_aggressor:
                target = max(min_raise, int(pot * river_frac * mult))
                if target < our_chips * 0.40:
                    return Decision("bet", amount=target, comment=f"[bluff] wolf river bluff")

    # ================================================================
    # STEAL / STAB: Bet when checked to in position (not PFR)
    # ================================================================
    if amount_to_call == 0 and position == Position.LATE and not _preflop_aggressor:
        # Opponents checked to us in position: stab at the pot
        if board.num_community == 3 and mult >= 0.8:
            # Stab flop with position advantage
            if board.high_card_rank >= 8 or board.is_rainbow:
                target = max(min_raise, int(pot * 0.40))
                if target < our_chips * 0.15:
                    return Decision("bet", amount=target, comment=f"[bluff] wolf position stab")

        if board.num_community == 4 and equity >= 0.15:
            # Turn stab when checked to twice
            if board.high_card_rank >= 9:
                target = max(min_raise, int(pot * 0.45))
                if target < our_chips * 0.20:
                    return Decision("bet", amount=target, comment=f"[bluff] wolf turn stab")

    # ================================================================
    # RAISE BLUFF: When facing a bet, sometimes raise as a bluff
    # ================================================================
    if (
        amount_to_call > 0
        and amount_to_call <= pot * 0.40
        and mult >= 0.9
        and avg_fold_pct >= 0.55
        and position == Position.LATE
        and active <= 1
    ):
        # Only with some equity (don't pure bluff raise with nothing)
        if equity >= 0.15 and (have_flush_draw or have_oesd):
            raise_to = max(min_raise, int(pot * 0.85))
            if raise_to < our_chips * 0.35:
                return Decision("raise", amount=raise_to, comment=f"[bluff] wolf raise bluff")

    return None


# ===================================================================
# Helpers
# ===================================================================

def _board_danger(board: BoardTexture) -> float:
    """Rate board danger 0.0 (dry) to 1.0 (very wet)."""
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
