"""Game engine wrapper for backtesting — runs poker games in-process."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Add server source to path so we can import the poker game engine directly
_server_src = str(Path(__file__).resolve().parent.parent.parent / "server" / "src")
if _server_src not in sys.path:
    sys.path.insert(0, _server_src)

from poker.game import Game  # noqa: E402
from bot.strategies import STRATEGIES  # noqa: E402


@dataclass
class HandLog:
    """Record of a single poker hand."""

    hand_number: int
    players_cards: dict[str, list[str]]  # name -> [card, card]
    community_cards: list[str]
    actions: list[dict]
    winners: list[str]
    pot: int


@dataclass
class GameResult:
    """Result of a complete poker game."""

    game_number: int
    winner: str
    hand_count: int
    chip_history: dict[str, list[int]]  # name -> chips after each hand
    hand_logs: list[HandLog] = field(default_factory=list)


def _build_state(game: Game, player_id: int) -> dict:
    """Build the state dict that bot strategies expect, directly from Game object."""
    hand = game.current_hand
    if hand is None:
        return {"game_over": True, "winner": game.winner}

    our_player = None
    for p in hand.players:
        if p.id == player_id:
            our_player = p
            break

    current_turn = hand.current_player.id if hand.current_player else None
    amount_to_call = hand.get_amount_to_call(player_id) if our_player else 0

    players = []
    for p in hand.players:
        players.append({
            "id": p.id,
            "name": p.name,
            "chips": p.chips,
            "current_bet": p.current_bet,
            "is_folded": p.is_folded,
            "is_all_in": p.is_all_in,
            "is_resigned": False,
        })

    recent_actions = []
    for a in hand.actions[-10:]:
        recent_actions.append({
            "player": a.player_name,
            "action": a.action,
            "amount": a.amount,
            "comment": getattr(a, "comment", None),
        })

    your_cards = [str(c) for c in our_player.hole_cards] if our_player else []
    community_cards = [str(c) for c in hand.community_cards]

    dealer_id = hand.players[hand.dealer_index].id

    min_raise = hand.current_bet + hand.min_raise_size
    if hand.current_bet == 0:
        min_raise = hand.min_raise_size

    return {
        "phase": hand.phase,
        "your_cards": your_cards,
        "community_cards": community_cards,
        "pot": hand.pot,
        "amount_to_call": amount_to_call,
        "min_raise": min_raise,
        "your_chips": our_player.chips if our_player else 0,
        "current_turn": current_turn,
        "dealer": dealer_id,
        "players": players,
        "recent_actions": recent_actions,
        "hand_number": game.hand_number,
        "is_your_turn": current_turn == player_id,
        "game_over": game.game_over,
        "winner": game.winner,
    }


def _collect_hand_log(game: Game, registered: dict) -> HandLog:
    """Snapshot the current hand state for logging."""
    hand = game.current_hand
    players_cards: dict[str, list[str]] = {}
    community: list[str] = []
    actions: list[dict] = []
    pot = 0

    if hand is not None:
        for p in hand.players:
            players_cards[p.name] = [str(c) for c in p.hole_cards]
        community = [str(c) for c in hand.community_cards]
        actions = [
            {
                "player": a.player_name,
                "action": a.action,
                "amount": a.amount,
            }
            for a in hand.actions
        ]
        pot = hand.pot

    return HandLog(
        hand_number=game.hand_number,
        players_cards=players_cards,
        community_cards=community,
        actions=actions,
        winners=[],  # filled in after hand completes
        pot=pot,
    )


def run_game(
    bot_names: list[str],
    game_number: int = 1,
    record_hands: bool = False,
    strategies: dict | None = None,
) -> GameResult:
    """Run a single poker game in-process. Returns structured result.

    strategies: optional {name_lower: (decide_fn, reset_fn)} dict.
                Defaults to STRATEGIES from bot.strategies.
    """
    strats = strategies or STRATEGIES
    game = Game(action_timeout=0)

    registered: dict[str, object] = {}
    for name in bot_names:
        p = game.register(name)
        registered[name] = p
        _, reset_fn = strats[name.lower()]
        reset_fn()

    game.start()

    chip_history: dict[str, list[int]] = {name: [] for name in bot_names}
    hand_logs: list[HandLog] = []
    prev_hand_number = 0
    current_hand_log: HandLog | None = None

    max_actions = 10_000
    actions = 0

    while not game.game_over and actions < max_actions:
        hand = game.current_hand
        if hand is None:
            break

        # Detect new hand — record chip snapshots and finalize previous hand log
        if game.hand_number != prev_hand_number:
            if current_hand_log is not None and record_hands:
                hand_logs.append(current_hand_log)
            for name in bot_names:
                pid = registered[name].id
                chips = 0
                for p in hand.players:
                    if p.id == pid:
                        chips = p.chips
                        break
                chip_history[name].append(chips)
            prev_hand_number = game.hand_number
            if record_hands:
                current_hand_log = _collect_hand_log(game, registered)

        cp = hand.current_player
        if cp is None:
            break

        strategy_key = cp.name.lower()
        if strategy_key not in strats:
            game.do_action(cp.id, "fold")
            actions += 1
            continue

        decide_fn, _ = strats[strategy_key]
        state = _build_state(game, cp.id)

        if state.get("game_over"):
            break

        try:
            decision = decide_fn(state)
        except Exception:
            log.warning("Strategy %s crashed, forcing fold", strategy_key, exc_info=True)
            decision = type("D", (), {"action": "fold", "amount": None, "comment": None})()

        result = game.do_action(
            cp.id,
            decision.action,
            amount=decision.amount,
            comment=decision.comment,
        )

        if result != "ok":
            log.debug("Action '%s' rejected for %s (result=%s), falling back", decision.action, strategy_key, result)
            fallback = "check" if state["amount_to_call"] == 0 else "fold"
            fb_result = game.do_action(cp.id, fallback)
            if fb_result != "ok":
                log.warning("Fallback '%s' also failed for %s, forcing fold", fallback, strategy_key)
                game.do_action(cp.id, "fold")

        actions += 1

        # After action, check if hand completed — capture winners
        if record_hands and current_hand_log is not None:
            if game.current_hand is not hand:
                # Hand just finished — update the log with final state
                current_hand_log.community_cards = [str(c) for c in hand.community_cards]
                current_hand_log.pot = hand.pot
                current_hand_log.actions = [
                    {
                        "player": a.player_name,
                        "action": a.action,
                        "amount": a.amount,
                    }
                    for a in hand.actions
                ]
                # Determine winners: players who weren't folded in a finished hand
                current_hand_log.winners = [
                    p.name for p in hand.players if not p.is_folded
                ]

    # Capture final hand log if game ended mid-hand
    if record_hands and current_hand_log is not None:
        if current_hand_log not in hand_logs:
            hand_logs.append(current_hand_log)

    return GameResult(
        game_number=game_number,
        winner=game.winner or "unknown",
        hand_count=game.hand_number,
        chip_history=chip_history,
        hand_logs=hand_logs,
    )
