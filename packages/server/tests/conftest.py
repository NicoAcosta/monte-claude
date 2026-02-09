import pytest
from poker.db import get_pool

TABLES = ["accounts", "balances", "game_events", "hand_summaries", "player_stats"]


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all tables between tests to ensure isolation."""
    pool = get_pool()
    with pool.connection() as conn:
        for table in TABLES:
            conn.execute(f"TRUNCATE {table} CASCADE")
        conn.commit()
    yield
