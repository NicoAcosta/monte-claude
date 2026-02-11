"""Fast in-process tournament: bypasses HTTP, runs games directly.

Usage: uv run python fast_tournament.py [--games N]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

# Add server source to path so we can import the game engine directly
sys.path.insert(0, "../server/src")

from poker.game import Game, SMALL_BLIND, BIG_BLIND  # noqa: E402
from bot.strategies import STRATEGIES  # noqa: E402

BOTS = ["Shark", "Wolf", "Fox", "Hawk"]

log = logging.getLogger("tournament")


def _build_state(game: Game, player_id: int, player_name: str) -> dict:
    """Build the state dict that bot strategies expect, directly from Game object."""
    hand = game.current_hand
    if hand is None:
        return {"game_over": True, "winner": game.winner}

    # Find our player in hand
    our_player = None
    for p in hand.players:
        if p.id == player_id:
            our_player = p
            break

    current_turn = hand.current_player.id if hand.current_player else None
    amount_to_call = hand.get_amount_to_call(player_id) if our_player else 0

    # Build players list
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

    # Recent actions
    recent_actions = []
    for a in hand.actions[-10:]:
        recent_actions.append({
            "player": a.player_name,
            "action": a.action,
            "amount": a.amount,
            "comment": getattr(a, "comment", None),
        })

    # Cards as strings
    your_cards = [str(c) for c in our_player.hole_cards] if our_player else []
    community_cards = [str(c) for c in hand.community_cards]

    # Dealer ID
    dealer_id = hand.players[hand.dealer_index].id

    # Min raise
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


def play_one_game(game_num: int) -> str:
    """Play a single 4-player game in-process. Returns winner name."""
    game = Game(action_timeout=0)  # No timeout

    # Register players
    registered = {}
    for bot_name in BOTS:
        p = game.register(bot_name)
        registered[bot_name] = p
        _, reset_fn = STRATEGIES[bot_name.lower()]
        reset_fn()

    game.start()

    max_actions = 10000  # Safety valve
    actions = 0

    while not game.game_over and actions < max_actions:
        hand = game.current_hand
        if hand is None:
            break

        cp = hand.current_player
        if cp is None:
            break

        # Find which bot this is
        bot_name = cp.name
        strategy_key = bot_name.lower()
        if strategy_key not in STRATEGIES:
            # Shouldn't happen, but safety
            game.do_action(cp.id, "fold")
            actions += 1
            continue

        decide_fn, _ = STRATEGIES[strategy_key]
        state = _build_state(game, cp.id, cp.name)

        if state.get("game_over"):
            break

        try:
            decision = decide_fn(state)
        except Exception:
            decision = type("D", (), {"action": "fold", "amount": None, "comment": None})()

        result = game.do_action(
            cp.id,
            decision.action,
            amount=decision.amount,
            comment=decision.comment,
        )

        if result != "ok":
            # Fallback
            fallback = "check" if state["amount_to_call"] == 0 else "fold"
            game.do_action(cp.id, fallback)

        actions += 1

    return game.winner or "unknown"


def main(num_games: int) -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    log.setLevel(logging.INFO)

    wins = {b: 0 for b in BOTS}

    log.info("=" * 60)
    log.info("  FAST TOURNAMENT: %s (%d games)", " vs ".join(BOTS), num_games)
    log.info("=" * 60)

    t0 = time.time()

    for i in range(1, num_games + 1):
        winner = play_one_game(i)

        matched = "???"
        for b in BOTS:
            if b.lower() in winner.lower():
                wins[b] += 1
                matched = b.upper()
                break

        if i % 10 == 0 or i == num_games:
            score = " | ".join(f"{b} {wins[b]}" for b in BOTS)
            elapsed = time.time() - t0
            log.info("Game %3d/%d (%4.1fs) | %s", i, num_games, elapsed, score)

    elapsed = time.time() - t0
    log.info("=" * 60)
    log.info("  FINAL: %s", " | ".join(f"{b} {wins[b]}" for b in BOTS))
    champion = max(wins, key=wins.get)
    log.info("  CHAMPION: %s with %d wins! (%.1f%%)", champion.upper(), wins[champion], 100 * wins[champion] / num_games)
    log.info("  Time: %.1fs (%.2fs/game)", elapsed, elapsed / num_games)
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=200, help="Number of games")
    args = parser.parse_args()
    main(args.games)
