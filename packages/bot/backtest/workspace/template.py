"""Strategy template — copy this file and implement your logic.

Rename to your bot name, e.g. `viper.py`, then implement decide().
The backtest lab will auto-discover it from the workspace/ directory.

Available imports (all from the bot package):
    from bot.equity import estimate_equity
    from bot.cards import rank_index, is_suited, is_pair, gap
    from bot.preflop_ranges import (
        classify_hand, determine_position, preflop_action,
        HandTier, Position, PreflopAction,
    )
    from bot.strategies.board import (
        analyze_board, has_flush, has_flush_draw,
        has_open_ended_straight_draw, has_overpair, has_top_pair,
        top_pair_kicker_strength, BoardTexture,
    )
    from bot.strategies.opponent import OpponentTracker, OpponentProfile
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.equity import estimate_equity
from bot.cards import rank_index, is_suited, is_pair, gap
from bot.preflop_ranges import (
    classify_hand,
    determine_position,
    preflop_action,
    HandTier,
    Position,
    PreflopAction,
)
from bot.strategies.board import (
    analyze_board,
    has_flush,
    has_flush_draw,
    has_open_ended_straight_draw,
    has_overpair,
    has_top_pair,
    top_pair_kicker_strength,
)
from bot.strategies.opponent import OpponentTracker, OpponentProfile

# ---------------------------------------------------------------------------
# Decision type (must be returned by decide())
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    action: str              # "check", "fold", "call", "bet", "raise", "all_in"
    amount: int | None = None
    comment: str | None = None


# ---------------------------------------------------------------------------
# Global state (persists across hands within one game, reset between games)
# ---------------------------------------------------------------------------

_tracker = OpponentTracker()

BIG_BLIND = 20


def reset_tracker() -> None:
    """Called before each new game to reset per-game state."""
    global _tracker
    _tracker = OpponentTracker()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def decide(state: dict[str, Any]) -> Decision:
    """Take game state, return a Decision.

    State fields:
        phase: str           - "preflop", "flop", "turn", "river"
        your_cards: [str]    - ["Ah", "Kd"]
        community_cards: [str]
        pot: int
        amount_to_call: int  - 0 means you can check
        min_raise: int
        your_chips: int
        players: [{id, name, chips, current_bet, is_folded, is_all_in}]
        dealer: int
        hand_number: int
        recent_actions: [{player, action, amount}]
        is_your_turn: bool
        current_turn: int|None - Player ID whose turn it is
        game_over: bool      - True when the game has ended
        winner: str|None     - Winner's name (only set when game_over)
    """
    _tracker.update(state)

    # --- Your strategy logic here ---

    # Example: fold or check everything (placeholder)
    if state["amount_to_call"] == 0:
        return Decision(action="check")
    return Decision(action="fold")
