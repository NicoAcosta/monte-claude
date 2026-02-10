"""Append-only store for bug reports and questions."""

from __future__ import annotations

from datetime import datetime, timezone

from psycopg_pool import ConnectionPool


class FeedbackStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def submit_bug(self, username: str, body: str) -> None:
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO bug_reports (username, body, created_at) VALUES (%s, %s, %s)",
                (username, body, now),
            )
            conn.commit()

    def submit_question(self, username: str, body: str) -> None:
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO questions (username, body, created_at) VALUES (%s, %s, %s)",
                (username, body, now),
            )
            conn.commit()
