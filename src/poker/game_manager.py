from __future__ import annotations

from dataclasses import dataclass

from poker.game import Game


@dataclass(frozen=True)
class GameSummary:
    id: int
    player_count: int
    player_names: tuple[str, ...]
    started: bool
    game_over: bool
    winner: str | None
    hand_number: int


class GameManager:
    def __init__(self) -> None:
        self._games: dict[int, Game] = {}
        self._next_id = 1

    def create_game(self) -> tuple[int, Game]:
        game_id = self._next_id
        self._next_id += 1
        game = Game()
        self._games[game_id] = game
        return game_id, game

    def get_game(self, game_id: int) -> Game | None:
        return self._games.get(game_id)

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
            )
            for gid, game in self._games.items()
        ]
