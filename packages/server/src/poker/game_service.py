"""Game lifecycle orchestration — create, join, start, action."""

from __future__ import annotations

from poker.balance_store import BalanceStore
from poker.game import Game, RegisteredPlayer
from poker.game_manager import GameManager
from poker.game_mode import GameMode
from poker.game_recorder import GameRecorder


def infer_mode(mode: str | None, token: str | None) -> str:
    """Infer game mode from request params.

    Raises ValueError if onchain mode requested without token.
    """
    if mode is not None:
        if mode == GameMode.ONCHAIN and not token:
            raise ValueError("On-chain mode requires a token address")
        return mode
    return GameMode.ONCHAIN if token else GameMode.OFFCHAIN


def create_game(
    manager: GameManager,
    max_players: int,
    token: str | None,
    buy_in: int,
    mode: str,
) -> tuple[int, Game]:
    """Create a game via the manager."""
    return manager.create_game(
        max_players=max_players,
        token=token,
        buy_in=buy_in,
        mode=mode,
    )


def join_game(
    game: Game,
    username: str,
    wallet_address: str | None,
    balance_store: BalanceStore,
    buy_in: int,
    mode: str | None,
    recorder: GameRecorder | None,
) -> RegisteredPlayer:
    """Join a game: debit balance, register player, record event.

    Raises ValueError on insufficient balance or registration failure.
    Refunds on registration failure.
    """
    # Off-chain: debit buy-in from balance before registering
    if mode == GameMode.OFFCHAIN and buy_in > 0:
        try:
            balance_store.debit(username, buy_in)
        except ValueError:
            raise ValueError(f"Insufficient balance (need {buy_in})")

    try:
        player = game.register(username, wallet_address=wallet_address)
    except ValueError:
        # Refund if registration failed
        if mode == GameMode.OFFCHAIN and buy_in > 0:
            balance_store.credit(username, buy_in)
        raise

    if recorder:
        recorder.on_event("player_joined", {
            "player_name": player.name,
            "player_id": player.id,
        })

    return player


def start_game(
    game: Game,
    mode: str | None,
    buy_in: int,
    recorder: GameRecorder | None,
) -> int:
    """Mark funded (for offchain) and start the game.

    Raises ValueError if game can't start.
    Returns hand number.
    """
    if mode == GameMode.OFFCHAIN and buy_in > 0:
        game.funded = True

    hand_num = game.start()

    if recorder:
        recorder.on_event("game_started", {
            "player_count": game.player_count,
            "player_names": [p.name for p in game._players],
        })

    return hand_num
