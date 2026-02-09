"""Database connection pool — singleton module."""
from __future__ import annotations

import os

from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        dsn = os.environ.get(
            "DATABASE_URL",
            "postgresql://poker:poker_dev@localhost:5432/claude_poker",
        )
        _pool = ConnectionPool(dsn, min_size=2, max_size=10, open=True)
    return _pool


def set_pool(pool: ConnectionPool) -> None:
    """Replace the global pool (used by tests)."""
    global _pool
    _pool = pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
