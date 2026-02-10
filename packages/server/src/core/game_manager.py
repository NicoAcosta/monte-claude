from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from core.game_config import GameConfig
from core.game_metadata_store import GameMetadataStore
from core.game_protocol import GameProtocol
from core.game_recorder import GameRecorder

GameFactory = Callable[..., GameProtocol]


@dataclass(frozen=True)
class GameSummary:
    id: str
    player_count: int
    player_names: tuple[str, ...]
    started: bool
    game_over: bool
    winner: str | None
    hand_number: int
    max_players: int = 0
    token: str | None = None
    buy_in: int = 0
    buy_in_display: str = ""
    token_symbol: str | None = None
    funded: bool = False
    mode: str | None = None
    game_type: str = "poker"


class GameManager:
    def __init__(
        self,
        recorder_factory: Callable[[str, str], GameRecorder] | None = None,
        metadata_store: GameMetadataStore | None = None,
    ) -> None:
        self._games: dict[str, GameProtocol] = {}
        self._configs: dict[str, GameConfig] = {}
        self._recorders: dict[str, GameRecorder] = {}
        self._game_types: dict[str, str] = {}
        self._factories: dict[str, GameFactory] = {}
        self._enabled_types: set[str] = set()
        self._recorder_factory = recorder_factory
        self._metadata_store = metadata_store

    def register_game_type(self, game_type: str, factory: GameFactory) -> None:
        """Register a factory for a game type (e.g. 'poker', 'dice').

        Automatically enables the game type for new game creation.
        """
        self._factories[game_type] = factory
        self._enabled_types.add(game_type)

    def enable_game_type(self, game_type: str) -> None:
        """Enable creation of new games for the given type.

        Raises ValueError if the game type has not been registered.
        """
        if game_type not in self._factories:
            raise ValueError(f"Unknown game type: {game_type!r}")
        self._enabled_types.add(game_type)

    def disable_game_type(self, game_type: str) -> None:
        """Disable creation of new games for the given type.

        Existing games of this type continue running until completion.
        """
        self._enabled_types.discard(game_type)

    def is_game_type_enabled(self, game_type: str) -> bool:
        return game_type in self._enabled_types

    @property
    def enabled_game_types(self) -> frozenset[str]:
        return frozenset(self._enabled_types)

    def create_game(
        self,
        game_type: str = "poker",
        max_players: int = 0,
        token: str | None = None,
        buy_in: int = 0,
        token_decimals: int = 0,
        token_symbol: str | None = None,
        mode: str | None = None,
        on_game_over: Callable[[GameProtocol, GameConfig], None] | None = None,
        action_timeout: float | None = None,
        extensions_per_player: int | None = None,
    ) -> tuple[str, GameProtocol, GameConfig]:
        if game_type not in self._enabled_types:
            if game_type in self._factories:
                raise ValueError(f"Game type {game_type!r} is currently disabled")
            raise ValueError(f"Unknown game type: {game_type!r}")

        factory = self._factories[game_type]

        game_id = uuid.uuid4().hex

        config = GameConfig(
            mode=mode or "offchain",
            buy_in=buy_in,
            max_players=max_players,
            token=token,
            token_decimals=token_decimals,
            token_symbol=token_symbol,
        )

        recorder: GameRecorder | None = None
        if self._recorder_factory:
            recorder = self._recorder_factory(game_id, game_type)
            self._recorders[game_id] = recorder

        meta = self._metadata_store

        def _event_callback(event_type: str, data: dict) -> None:
            if event_type == "hand_completed" and config.token_symbol:
                data["token_symbol"] = config.token_symbol
            if recorder:
                recorder.on_event(event_type, data)
            if meta:
                if event_type == "game_started":
                    meta.update_started(game_id)
                elif event_type == "hand_started":
                    meta.update_hand_number(game_id, data.get("hand_number", 0))
                elif event_type == "game_over":
                    meta.update_game_over(game_id, data.get("winner"))
            if event_type == "game_over" and on_game_over is not None:
                on_game_over(game, config)

        kwargs: dict = {"event_callback": _event_callback}
        if action_timeout is not None:
            kwargs["action_timeout"] = action_timeout
        if extensions_per_player is not None:
            kwargs["extensions_per_player"] = extensions_per_player
        game = factory(**kwargs)

        self._games[game_id] = game
        self._configs[game_id] = config
        self._game_types[game_id] = game_type

        if meta:
            meta.create(
                game_id=game_id,
                mode=config.mode,
                buy_in=config.buy_in,
                max_players=config.max_players,
                token=config.token,
                token_decimals=config.token_decimals,
                token_symbol=config.token_symbol,
                action_timeout=action_timeout,
                extensions_per_player=extensions_per_player,
                game_type=game_type,
            )

        return game_id, game, config

    def get_recorder(self, game_id: str) -> GameRecorder | None:
        return self._recorders.get(game_id)

    def get_game(self, game_id: str) -> GameProtocol | None:
        return self._games.get(game_id)

    def get_game_type(self, game_id: str) -> str | None:
        return self._game_types.get(game_id)

    def get_config(self, game_id: str) -> GameConfig | None:
        return self._configs.get(game_id)

    def cleanup_completed(self, keep_recent: int = 5) -> int:
        """Remove completed games from memory, keeping the N most recent. Returns count removed."""
        completed = [
            gid for gid, game in self._games.items()
            if game.game_over
        ]
        to_remove = completed[:-keep_recent] if len(completed) > keep_recent else []
        for gid in to_remove:
            del self._games[gid]
            self._configs.pop(gid, None)
            self._recorders.pop(gid, None)
            self._game_types.pop(gid, None)
        return len(to_remove)

    def list_games(self) -> list[GameSummary]:
        return [
            GameSummary(
                id=gid,
                player_count=game.player_count,
                player_names=tuple(p.name for p in game.players),
                started=game.started,
                game_over=game.game_over,
                winner=game.winner,
                hand_number=game.hand_number,
                max_players=self._configs[gid].max_players,
                token=self._configs[gid].token,
                buy_in=self._configs[gid].buy_in,
                buy_in_display=self._configs[gid].buy_in_display,
                token_symbol=self._configs[gid].token_symbol,
                funded=self._configs[gid].funded,
                mode=self._configs[gid].mode,
                game_type=self._game_types.get(gid, "poker"),
            )
            for gid, game in self._games.items()
        ]
