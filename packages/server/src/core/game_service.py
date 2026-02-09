"""Game lifecycle orchestration — create, join, start, action."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from core.balance_store import BalanceStore
from core.game_protocol import GameProtocol, RegisteredPlayer
from core.game_config import GameConfig
from core.game_manager import GameManager
from core.game_metadata_store import GameMetadataStore
from core.game_mode import GameMode
from core.game_recorder import GameRecorder

if TYPE_CHECKING:
    pass

# Allowed modes per game type.  Validated in infer_mode().
GAME_ALLOWED_MODES: dict[str, frozenset[str]] = {
    "poker": frozenset({GameMode.OFFCHAIN, GameMode.ONCHAIN}),
    "dice": frozenset({GameMode.OFFCHAIN}),
}


def infer_mode(mode: str | None, token: str | None, game_type: str = "poker") -> str:
    """Infer game mode from request params.

    Raises ValueError if onchain mode requested without token or if mode
    is not allowed for the game type.
    """
    if mode is not None:
        if mode == GameMode.ONCHAIN and not token:
            raise ValueError("On-chain mode requires a token address")
        allowed = GAME_ALLOWED_MODES.get(game_type, frozenset({GameMode.OFFCHAIN}))
        if mode not in allowed:
            raise ValueError(f"Mode '{mode}' is not supported for {game_type} games")
        return mode
    return GameMode.ONCHAIN if token else GameMode.OFFCHAIN


def create_game(
    manager: GameManager,
    max_players: int,
    token: str | None,
    buy_in: int,
    mode: str,
    game_type: str = "poker",
    token_decimals: int = 0,
    token_symbol: str | None = None,
    on_game_over: Callable[[GameProtocol, GameConfig], None] | None = None,
    action_timeout: float | None = None,
    extensions_per_player: int | None = None,
) -> tuple[int, GameProtocol, GameConfig]:
    """Create a game via the manager."""
    return manager.create_game(
        game_type=game_type,
        max_players=max_players,
        token=token,
        buy_in=buy_in,
        token_decimals=token_decimals,
        token_symbol=token_symbol,
        mode=mode,
        on_game_over=on_game_over,
        action_timeout=action_timeout,
        extensions_per_player=extensions_per_player,
    )


def join_game(
    game: GameProtocol,
    config: GameConfig,
    username: str,
    wallet_address: str | None,
    balance_store: BalanceStore,
    recorder: GameRecorder | None,
    metadata_store: GameMetadataStore | None = None,
    game_id: int = 0,
) -> RegisteredPlayer:
    """Join a game: check capacity/mode, debit balance, register player, record event.

    Raises ValueError on insufficient balance, capacity, mode, or registration failure.
    Refunds on registration failure.
    """
    if config.is_at_capacity(game.player_count):
        raise ValueError("Game is full")
    if config.mode == GameMode.ONCHAIN and not wallet_address:
        raise ValueError("Wallet address required for on-chain games")

    # Off-chain: debit buy-in from balance before registering
    if config.mode == GameMode.OFFCHAIN and config.buy_in > 0:
        try:
            balance_store.debit(username, config.buy_in, reason="game_buy_in")
        except ValueError:
            raise ValueError(f"Insufficient balance (need {config.buy_in})")

    try:
        player = game.register(username, wallet_address=wallet_address)
    except ValueError:
        # Refund if registration failed
        if config.mode == GameMode.OFFCHAIN and config.buy_in > 0:
            balance_store.credit(username, config.buy_in, reason="join_refund")
        raise

    if recorder:
        recorder.on_event("player_joined", {
            "player_name": player.name,
            "player_id": player.id,
        })

    if metadata_store and game_id:
        metadata_store.update_player_joined(game_id, player.name)

    return player


def start_game(
    game: GameProtocol,
    config: GameConfig,
    recorder: GameRecorder | None,
    metadata_store: GameMetadataStore | None = None,
    game_id: int = 0,
) -> int:
    """Check funding, mark funded (for offchain), and start the game.

    Raises ValueError if game can't start.
    Returns hand number.
    """
    if config.mode == GameMode.OFFCHAIN and config.buy_in > 0:
        config.funded = True
    elif config.buy_in > 0 and not config.funded:
        raise ValueError("Deposits not confirmed")

    if metadata_store and game_id and config.funded:
        metadata_store.update_funded(game_id)

    hand_num = game.start()

    if recorder:
        recorder.on_event("game_started", {
            "player_count": game.player_count,
            "player_names": [p.name for p in game.players],
        })

    if metadata_store and game_id:
        metadata_store.update_started(game_id)

    return hand_num
