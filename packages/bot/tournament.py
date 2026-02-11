"""4-player tournament: Shark vs Wolf vs Fox vs Hawk, best-of-N.

Usage: uv run python tournament.py [--games N]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys

from bot.client import ApiError, Client
from bot.strategies import STRATEGIES

GAME_SERVER = "http://localhost:8001"
ACCOUNT_SERVER = "http://localhost:8002"
POLL_INTERVAL = 0.02

BOTS = ["Shark", "Wolf", "Fox", "Hawk"]

log = logging.getLogger("tournament")


async def run_bot(
    client: Client,
    game_id: str,
    api_key: str,
    decide_fn,
) -> str | None:
    while True:
        try:
            state = await client.get_state(game_id, api_key)
        except ApiError as e:
            if e.status in (502, 503, 504):
                await asyncio.sleep(1.0)
                continue
            raise

        if state["game_over"]:
            return state.get("winner", "unknown")

        if not state["is_your_turn"]:
            await asyncio.sleep(POLL_INTERVAL)
            continue

        decision = decide_fn(state)

        try:
            await client.do_action(
                game_id, api_key,
                action=decision.action,
                amount=decision.amount,
                comment=decision.comment,
            )
        except ApiError as e:
            if e.status == 409:
                continue
            if e.status == 400:
                fallback = "check" if state["amount_to_call"] == 0 else "fold"
                await client.do_action(game_id, api_key, action=fallback)
                continue
            raise

        await asyncio.sleep(0.005)


async def play_one_game(client: Client, keys: dict[str, str], game_num: int) -> str:
    """Play a single 4-player game. Returns winner name."""
    creator_key = keys[BOTS[0]]
    game_id = await client.create_game(creator_key, max_players=len(BOTS))

    for bot_name in BOTS:
        await client.join_game(game_id, keys[bot_name])

    # Reset all trackers
    for bot_name in BOTS:
        _, reset_fn = STRATEGIES[bot_name.lower()]
        reset_fn()

    await client.start_game(game_id, creator_key)

    tasks = []
    for bot_name in BOTS:
        decide_fn, _ = STRATEGIES[bot_name.lower()]
        tasks.append(run_bot(client, game_id, keys[bot_name], decide_fn))

    results = await asyncio.gather(*tasks)
    return next((r for r in results if r), "unknown")


async def main(num_games: int) -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    log.setLevel(logging.INFO)

    client = Client(game_server=GAME_SERVER, account_server=ACCOUNT_SERVER)
    wins: dict[str, int] = {b: 0 for b in BOTS}

    try:
        tag = random.randint(100, 999)
        keys = {}
        for bot_name in BOTS:
            keys[bot_name] = await client.register(f"{bot_name}T{tag}")

        log.info("=" * 60)
        log.info("  TOURNAMENT: %s (%d games)", " vs ".join(BOTS), num_games)
        log.info("=" * 60)

        for i in range(1, num_games + 1):
            winner = await play_one_game(client, keys, i)

            # Match winner to bot name
            matched = "???"
            for b in BOTS:
                if b.lower() in winner.lower():
                    wins[b] += 1
                    matched = b.upper()
                    break

            score = " | ".join(f"{b} {wins[b]}" for b in BOTS)
            log.info("Game %2d/%d: %-6s wins | %s", i, num_games, matched, score)

        log.info("=" * 60)
        log.info("  FINAL: %s", " | ".join(f"{b} {wins[b]}" for b in BOTS))
        champion = max(wins, key=wins.get)
        log.info("  CHAMPION: %s with %d wins!", champion.upper(), wins[champion])
        log.info("=" * 60)

    except ApiError as e:
        log.error("API error: %s", e)
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=10, help="Number of games")
    args = parser.parse_args()
    asyncio.run(main(args.games))
