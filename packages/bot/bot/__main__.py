"""Entry point: python -m bot --server URL --game-id N

Supports both CLI args and env vars (for Docker):
  BOT_SERVER, BOT_ACCOUNT_SERVER, BOT_GAME_ID, BOT_USERNAME, BOT_API_KEY, BOT_VERBOSE
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from .client import ApiError, Client
from .names import pick_name
from .strategy import decide

log = logging.getLogger("bot")

POLL_INTERVAL = 0.5


async def _ensure_balance(client: Client, api_key: str) -> bool:
    """Claim faucet if balance is zero. Returns False if faucet quota exhausted."""
    try:
        balance = await client.get_balance(api_key)
    except ApiError:
        # Account API might not require balance for free games — continue
        return True

    if balance > 0:
        return True

    log.info("Balance is 0, claiming faucet ...")
    try:
        resp = await client.claim_faucet(api_key)
        log.info("Faucet claimed! New balance: %d", resp["new_balance"])
        return True
    except ApiError as e:
        if e.status == 429:
            log.warning("Faucet quota exhausted: %s", e.detail)
            return False
        raise


async def run(args: argparse.Namespace) -> None:
    server = args.server
    account_server = args.account_server or server.replace(":8001", ":8002")

    client = Client(server, account_server=account_server)

    try:
        # Register or reuse key
        api_key = args.api_key
        username = args.username
        if not api_key:
            log.info("Registering as %s ...", username)
            api_key = await client.register(username)
            log.info("Registered. API key: %s", api_key)

        # Ensure we have tokens
        if not await _ensure_balance(client, api_key):
            log.error("No tokens and faucet exhausted. Shutting down.")
            sys.exit(0)

        # Join game
        game_id = args.game_id
        log.info("Joining game %d ...", game_id)
        join_resp = await client.join_game(game_id, api_key)
        player_id = join_resp["player_id"]
        log.info("Joined as player %d (%s)", player_id, join_resp["name"])

        # Wait for start
        log.info("Waiting for game to start ...")
        await client.wait_for_start(game_id)
        log.info("Game started!")

        # Main game loop
        await _game_loop(client, game_id, api_key)

    except ApiError as e:
        log.error("API error: %s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("Interrupted.")
    finally:
        await client.close()


async def _game_loop(client: Client, game_id: int, api_key: str) -> None:
    """Poll state and act when it's our turn."""
    last_hand = -1

    while True:
        try:
            state = await client.get_state(game_id, api_key)
        except ApiError as e:
            if e.status in (502, 503, 504):
                log.warning("Server error %d, retrying ...", e.status)
                await asyncio.sleep(2.0)
                continue
            raise

        if state["game_over"]:
            log.info("Game over! Winner: %s", state.get("winner", "unknown"))
            return

        hand = state["hand_number"]
        if hand != last_hand:
            last_hand = hand
            log.info(
                "── Hand %d | Phase: %s | Cards: %s | Chips: %d",
                hand, state["phase"], state["your_cards"], state["your_chips"],
            )

        if not state["is_your_turn"]:
            await asyncio.sleep(POLL_INTERVAL)
            continue

        # It's our turn — decide and act
        decision = decide(state)
        log.info(
            "Action: %s %s %s",
            decision.action,
            f"({decision.amount})" if decision.amount else "",
            decision.comment or "",
        )

        try:
            await client.do_action(
                game_id,
                api_key,
                action=decision.action,
                amount=decision.amount,
                comment=decision.comment,
            )
        except ApiError as e:
            if e.status == 409:
                log.warning("Stale state (409), re-polling ...")
                continue
            if e.status == 400:
                log.warning("Bad action (400: %s), falling back to fold/check", e.detail)
                fallback = "check" if state["amount_to_call"] == 0 else "fold"
                await client.do_action(game_id, api_key, action=fallback)
                continue
            raise

        # Small delay after acting to avoid hammering
        await asyncio.sleep(0.2)


def _env(name: str, default: str = "") -> str:
    """Read env var with BOT_ prefix."""
    return os.environ.get(f"BOT_{name}", default)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Equity-based poker bot for Monteclaude",
    )
    parser.add_argument(
        "--server", default=_env("SERVER") or None,
        help="Game API URL (env: BOT_SERVER)",
    )
    parser.add_argument(
        "--account-server", default=_env("ACCOUNT_SERVER") or None,
        help="Account API URL (env: BOT_ACCOUNT_SERVER)",
    )
    parser.add_argument(
        "--game-id", type=int, default=_env("GAME_ID") or None,
        help="Game ID to join (env: BOT_GAME_ID)",
    )
    parser.add_argument(
        "--username", default=_env("USERNAME") or None,
        help="Bot username — omit for auto-generated unique name (env: BOT_USERNAME)",
    )
    parser.add_argument(
        "--api-key", default=_env("API_KEY") or None,
        help="Reuse an existing API key (env: BOT_API_KEY)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=_env("VERBOSE").lower() in ("1", "true", "yes"),
        help="Enable debug logging (env: BOT_VERBOSE)",
    )

    args = parser.parse_args()

    if not args.server:
        parser.error("--server is required (or set BOT_SERVER)")
    if args.game_id is None:
        parser.error("--game-id is required (or set BOT_GAME_ID)")
    args.game_id = int(args.game_id)

    # Auto-generate unique username if not specified
    if not args.username:
        args.username = pick_name()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
