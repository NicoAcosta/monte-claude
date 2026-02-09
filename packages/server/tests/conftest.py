import pytest
from core.account_store import AccountStore
from core.db import get_pool

TABLES = [
    "balance_history", "auth_events", "escrow_operations",
    "accounts", "balances", "game_events", "hand_summaries",
    "player_stats", "player_token_stats", "game_metadata", "streams",
]


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
    # Clear rate limiters used by account_api
    from account_api.app import _register_limiter, _faucet_limiter
    _register_limiter.clear()
    _faucet_limiter.clear()
    yield


@pytest.fixture
def make_account():
    """Create a test account, return username."""
    pool = get_pool()
    store = AccountStore(pool)
    created: set[str] = set()

    def _make(username: str) -> str:
        if username not in created:
            try:
                store.create_account(username)
            except ValueError:
                pass
            created.add(username)
        return username

    return _make
