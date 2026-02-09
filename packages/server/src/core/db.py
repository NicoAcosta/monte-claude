"""Database connection pool — singleton module."""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager

from psycopg_pool import ConnectionPool

_log = logging.getLogger("poker.db")

_pool: ConnectionPool | None = None

_CONNECT_RETRIES = int(os.environ.get("DB_CONNECT_RETRIES", "3"))
_CONNECT_RETRY_DELAY = float(os.environ.get("DB_CONNECT_RETRY_DELAY", "2"))
_SLOW_QUERY_MS = float(os.environ.get("SLOW_QUERY_MS", "100"))


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        dsn = os.environ.get(
            "DATABASE_URL",
            "postgresql://poker:poker_dev@localhost:5432/monteclaude",
        )
        last_err: Exception | None = None
        for attempt in range(1, _CONNECT_RETRIES + 1):
            try:
                _pool = ConnectionPool(dsn, min_size=2, max_size=10, open=True)
                if attempt > 1:
                    _log.info("db_connected attempt=%d", attempt)
                return _pool
            except Exception as exc:
                last_err = exc
                _log.warning(
                    "db_connect_failed attempt=%d/%d err=%s",
                    attempt, _CONNECT_RETRIES, exc,
                )
                if attempt < _CONNECT_RETRIES:
                    time.sleep(_CONNECT_RETRY_DELAY)
        raise RuntimeError(f"Failed to connect to database after {_CONNECT_RETRIES} attempts") from last_err
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


@contextmanager
def timed_query(description: str):
    """Context manager that logs a warning if a query exceeds the slow threshold."""
    t0 = time.monotonic()
    yield
    elapsed_ms = (time.monotonic() - t0) * 1000
    if elapsed_ms > _SLOW_QUERY_MS:
        _log.warning("slow_query description=%s elapsed_ms=%.1f", description, elapsed_ms)
