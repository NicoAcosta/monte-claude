"""Stream store — DB-backed stream persistence replacing StreamManager."""

from __future__ import annotations

import time

from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from poker.stream import Stream


@dataclass(frozen=True)
class StreamSummary:
    id: int
    game_id: int
    host_username: str
    title: str


class StreamStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create(self, game_id: int, host_username: str, title: str) -> Stream:
        created_at = time.time()
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    """INSERT INTO streams (game_id, host_username, title, created_at)
                       VALUES (%s, %s, %s, %s)
                       RETURNING id""",
                    (game_id, host_username, title, created_at),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise ValueError(f"User '{host_username}' already has a stream on this game")
        return Stream(
            id=row[0],
            game_id=game_id,
            host_username=host_username,
            title=title,
            created_at=created_at,
        )

    def get(self, stream_id: int) -> Stream | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT id, game_id, host_username, title, commentary_text, created_at "
                "FROM streams WHERE id = %s",
                (stream_id,),
            ).fetchone()
        if row is None:
            return None
        return Stream(
            id=row[0], game_id=row[1], host_username=row[2],
            title=row[3], commentary_text=row[4], created_at=row[5],
        )

    def update_commentary(self, stream_id: int, text: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE streams SET commentary_text = %s WHERE id = %s",
                (text, stream_id),
            )
            conn.commit()

    def list_for_game(self, game_id: int) -> list[StreamSummary]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, game_id, host_username, title FROM streams WHERE game_id = %s ORDER BY id",
                (game_id,),
            ).fetchall()
        return [StreamSummary(id=r[0], game_id=r[1], host_username=r[2], title=r[3]) for r in rows]

    def list_all(self) -> list[StreamSummary]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, game_id, host_username, title FROM streams ORDER BY id",
            ).fetchall()
        return [StreamSummary(id=r[0], game_id=r[1], host_username=r[2], title=r[3]) for r in rows]
