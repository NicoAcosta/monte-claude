from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from poker.game import Game
from poker.game_config import GameConfig
from poker.game_recorder import GameRecorder


@dataclass(frozen=True)
class GameSummary:
    id: int
    player_count: int
    player_names: tuple[str, ...]
    started: bool
    game_over: bool
    winner: str | None
    hand_number: int
    max_players: int = 0
    token: str | None = None
    buy_in: int = 0
    funded: bool = False
    mode: str | None = None


class GameManager:
    def __init__(
        self,
        recorder_factory: Callable[[int], GameRecorder] | None = None,
    ) -> None:
        self._games: dict[int, Game] = {}
        self._configs: dict[int, GameConfig] = {}
        self._recorders: dict[int, GameRecorder] = {}
        self._next_id = 1
        self._recorder_factory = recorder_factory

    def create_game(
        self,
        max_players: int = 0,
        token: str | None = None,
        buy_in: int = 0,
        mode: str | None = None,
    ) -> tuple[int, Game, GameConfig]:
        game_id = self._next_id
        self._next_id += 1

        config = GameConfig(
            mode=mode or "offchain",
            buy_in=buy_in,
            max_players=max_players,
            token=token,
        )

        if self._recorder_factory:
            recorder = self._recorder_factory(game_id)
            self._recorders[game_id] = recorder
            game = Game(event_callback=recorder.on_event)
        else:
            game = Game()

        self._games[game_id] = game
        self._configs[game_id] = config
        return game_id, game, config

    def get_recorder(self, game_id: int) -> GameRecorder | None:
        return self._recorders.get(game_id)

    def get_game(self, game_id: int) -> Game | None:
        return self._games.get(game_id)

    def get_config(self, game_id: int) -> GameConfig | None:
        return self._configs.get(game_id)

    def list_games(self) -> list[GameSummary]:
        return [
            GameSummary(
                id=gid,
                player_count=game.player_count,
                player_names=tuple(p.name for p in game._players),
                started=game.started,
                game_over=game.game_over,
                winner=game.winner,
                hand_number=game.hand_number,
                max_players=self._configs[gid].max_players,
                token=self._configs[gid].token,
                buy_in=self._configs[gid].buy_in,
                funded=self._configs[gid].funded,
                mode=self._configs[gid].mode,
            )
            for gid, game in self._games.items()
        ]
