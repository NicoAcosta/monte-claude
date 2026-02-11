"""Local match orchestrator: Shark bot vs Equity bot.

Creates a game, registers two bots, and runs them head-to-head.
Usage: uv run python play_local.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

from bot.client import ApiError, Client
from bot.strategy import decide as equity_decide
from bot.strategies.shark import decide as shark_decide, Decision, reset_tracker

GAME_SERVER = "http://localhost:8001"
ACCOUNT_SERVER = "http://localhost:8002"
POLL_INTERVAL = 0.3

log = logging.getLogger("match")


async def run_bot(
    name: str,
    client: Client,
    game_id: str,
    api_key: str,
    decide_fn,
) -> str | None:
    """Run a single bot until game over. Returns winner name or None."""
    last_hand = -1
    bot_log = logging.getLogger(f"bot.{name}")

    while True:
        try:
            state = await client.get_state(game_id, api_key)
        except ApiError as e:
            if e.status in (502, 503, 504):
                bot_log.warning("Server error %d, retrying ...", e.status)
                await asyncio.sleep(2.0)
                continue
            raise

        if state["game_over"]:
            winner = state.get("winner", "unknown")
            bot_log.info("Game over! Winner: %s", winner)
            return winner

        hand = state["hand_number"]
        if hand != last_hand:
            last_hand = hand
            bot_log.info(
                "Hand %d | %s | Cards: %s | Chips: %d",
                hand, state["phase"], state["your_cards"], state["your_chips"],
            )

        if not state["is_your_turn"]:
            await asyncio.sleep(POLL_INTERVAL)
            continue

        decision = decide_fn(state)
        bot_log.info(
            "=> %s %s %s",
            decision.action,
            f"({decision.amount})" if decision.amount else "",
            decision.comment or "",
        )

        try:
            await client.do_action(
                game_id, api_key,
                action=decision.action,
                amount=decision.amount,
                comment=decision.comment,
            )
        except ApiError as e:
            if e.status == 409:
                bot_log.warning("Stale state (409), re-polling ...")
                continue
            if e.status == 400:
                bot_log.warning("Bad action (400: %s), fallback", e.detail)
                fallback = "check" if state["amount_to_call"] == 0 else "fold"
                await client.do_action(game_id, api_key, action=fallback)
                continue
            raise

        await asyncio.sleep(0.15)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)-15s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    client = Client(game_server=GAME_SERVER, account_server=ACCOUNT_SERVER)

    try:
        # 1. Register both bots
        log.info("Registering bots ...")
        shark_key = await client.register("SharkBot")
        equity_key = await client.register("EquityBot")
        log.info("SharkBot key: %s", shark_key[:12] + "...")
        log.info("EquityBot key: %s", equity_key[:12] + "...")

        # 2. Create a game
        log.info("Creating game ...")
        game_id = await client.create_game(shark_key, max_players=2)
        log.info("Game ID: %s", game_id)

        # 3. Join both bots
        log.info("Joining bots to game ...")
        r1 = await client.join_game(game_id, shark_key)
        r2 = await client.join_game(game_id, equity_key)
        log.info("SharkBot joined as player %d", r1["player_id"])
        log.info("EquityBot joined as player %d", r2["player_id"])

        # 4. Start the game
        log.info("Starting game ...")
        await client.start_game(game_id, shark_key)
        log.info("Game started!")

        # 5. Reset shark tracker for fresh game
        reset_tracker()

        # 6. Run both bots concurrently
        log.info("=" * 60)
        log.info("  SHARK BOT  vs  EQUITY BOT  --  FIGHT!")
        log.info("=" * 60)

        results = await asyncio.gather(
            run_bot("SharkBot", client, game_id, shark_key, shark_decide),
            run_bot("EquityBot", client, game_id, equity_key, equity_decide),
        )

        winner = results[0] or results[1]
        log.info("=" * 60)
        log.info("  WINNER: %s", winner)
        log.info("=" * 60)

    except ApiError as e:
        log.error("API error: %s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("Interrupted.")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
