import pytest
from poker.db import get_pool

TABLES = ["accounts", "balances", "game_events", "hand_summaries", "player_stats", "player_token_stats", "game_metadata", "streams"]


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all tables and clear caches between tests for isolation."""
    pool = get_pool()
    with pool.connection() as conn:
        for table in TABLES:
            conn.execute(f"TRUNCATE {table} CASCADE")
        conn.commit()
    # Clear in-process TTL cache used by data_api
    from data_api.app import _cache
    _cache.clear()
    yield
