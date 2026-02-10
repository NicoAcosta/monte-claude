"""Audit stores for auth events and escrow operations."""

from __future__ import annotations

from datetime import datetime, timezone

from psycopg_pool import ConnectionPool


class AuthAuditStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def record(
        self,
        event_type: str,
        *,
        username: str | None = None,
        ip: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO auth_events (username, event_type, ip_address, created_at)
                   VALUES (%s, %s, %s, %s)""",
                (username, event_type, ip, now),
            )
            conn.commit()


class EscrowAuditStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def record(
        self,
        game_id: str,
        operation: str,
        *,
        escrow_address: str | None = None,
        details: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO escrow_operations (game_id, operation, escrow_address, details, created_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (game_id, operation, escrow_address, details, now),
            )
            conn.commit()
