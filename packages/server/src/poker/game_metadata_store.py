"""Game metadata store — lobby data persisted in PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import ConnectionPool


@dataclass(frozen=True)
class GameMetadata:
    game_id: int
    mode: str
    buy_in: int
    max_players: int
    token: str | None
    token_decimals: int
    token_symbol: str | None
    player_count: int
    player_names: list[str]
    started: bool
    game_over: bool
    winner: str | None
    hand_number: int
    funded: bool
    escrow_address: str | None
    action_timeout: float | None


class GameMetadataStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create(
        self,
        game_id: int,
        mode: str,
        buy_in: int,
        max_players: int,
        token: str | None = None,
        token_decimals: int = 0,
        token_symbol: str | None = None,
        action_timeout: float | None = None,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO game_metadata
                   (game_id, mode, buy_in, max_players, token, token_decimals, token_symbol, action_timeout)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (game_id, mode, buy_in, max_players, token, token_decimals, token_symbol, action_timeout),
            )
            conn.commit()

    def update_player_joined(self, game_id: int, player_name: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """UPDATE game_metadata
                   SET player_names = array_append(player_names, %s),
                       player_count = player_count + 1,
                       updated_at = NOW()
                   WHERE game_id = %s""",
                (player_name, game_id),
            )
            conn.commit()

    def update_started(self, game_id: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE game_metadata SET started = TRUE, updated_at = NOW() WHERE game_id = %s",
                (game_id,),
            )
            conn.commit()

    def update_hand_number(self, game_id: int, hand_number: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE game_metadata SET hand_number = %s, updated_at = NOW() WHERE game_id = %s",
                (hand_number, game_id),
            )
            conn.commit()

    def update_game_over(self, game_id: int, winner: str | None) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE game_metadata SET game_over = TRUE, winner = %s, updated_at = NOW() WHERE game_id = %s",
                (winner, game_id),
            )
            conn.commit()

    def update_funded(self, game_id: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE game_metadata SET funded = TRUE, updated_at = NOW() WHERE game_id = %s",
                (game_id,),
            )
            conn.commit()

    def list_all(self) -> list[GameMetadata]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """SELECT game_id, mode, buy_in, max_players, token, token_decimals,
                          token_symbol, player_count, player_names, started, game_over,
                          winner, hand_number, funded, escrow_address, action_timeout
                   FROM game_metadata ORDER BY game_id""",
            ).fetchall()
        return [
            GameMetadata(
                game_id=r[0], mode=r[1], buy_in=r[2], max_players=r[3],
                token=r[4], token_decimals=r[5], token_symbol=r[6],
                player_count=r[7], player_names=list(r[8]) if r[8] else [],
                started=r[9], game_over=r[10], winner=r[11],
                hand_number=r[12], funded=r[13], escrow_address=r[14],
                action_timeout=r[15],
            )
            for r in rows
        ]

    def exists(self, game_id: int) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM game_metadata WHERE game_id = %s",
                (game_id,),
            ).fetchone()
        return row is not None
