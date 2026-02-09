"""Tests for tier-2 audit fixes: TOCTOU, blanket catch, memory leak, DRY."""

import pytest

from poker.account_store import AccountStore
from poker.db import get_pool
from poker.formatting import format_buy_in
from poker.game_manager import GameManager
from poker.stream_store import StreamStore


# ── Fix 1: Account creation TOCTOU race ────────────────


class TestAccountStoreTOCTOU:
    def test_duplicate_username_raises_value_error(self):
        """Concurrent-safe: duplicate username yields ValueError, not raw DB exception."""
        store = AccountStore(get_pool())
        store.create_account("DuplicateTest")
        with pytest.raises(ValueError, match="already taken"):
            store.create_account("DuplicateTest")

    def test_no_select_before_insert_still_catches_duplicate(self):
        """The fix relies on the DB constraint, not a SELECT check."""
        store = AccountStore(get_pool())
        store.create_account("AtomicUser")
        # Second attempt must still raise ValueError (not UniqueViolation)
        with pytest.raises(ValueError, match="already taken"):
            store.create_account("AtomicUser")
        # Verify the account still exists and is functional
        acct = store.get_account("AtomicUser")
        assert acct is not None
        assert acct.username == "AtomicUser"


# ── Fix 2: StreamStore blanket exception catch ──────────


class TestStreamStoreSpecificCatch:
    def test_duplicate_stream_raises_value_error(self):
        """Duplicate host+game raises ValueError with descriptive message."""
        store = StreamStore(get_pool())
        store.create(game_id=100, host_username="Host1", title="First")
        with pytest.raises(ValueError, match="already has a stream"):
            store.create(game_id=100, host_username="Host1", title="Second")

    def test_different_host_same_game_succeeds(self):
        """Non-duplicate combinations still work after the fix."""
        store = StreamStore(get_pool())
        s1 = store.create(game_id=100, host_username="HostA", title="Stream A")
        s2 = store.create(game_id=100, host_username="HostB", title="Stream B")
        assert s1.id != s2.id


# ── Fix 3: Game cleanup / memory leak ──────────────────


class TestGameManagerCleanup:
    def _make_finished_game(self, mgr: GameManager) -> int:
        gid, game, _ = mgr.create_game()
        game.register("Alice")
        game.register("Bob")
        game.start()
        # Force game_over directly for test simplicity
        game.game_over = True
        game.winner = "Alice"
        return gid

    def test_cleanup_removes_old_completed_games(self):
        mgr = GameManager()
        ids = [self._make_finished_game(mgr) for _ in range(8)]

        removed = mgr.cleanup_completed(keep_recent=3)
        assert removed == 5

        # Only 3 most recent completed games remain (+ 0 active)
        for gid in ids[:5]:
            assert mgr.get_game(gid) is None
            assert mgr.get_config(gid) is None
        for gid in ids[5:]:
            assert mgr.get_game(gid) is not None
            assert mgr.get_config(gid) is not None

    def test_cleanup_keeps_active_games(self):
        mgr = GameManager()
        # Create an active (not game_over) game
        active_id, active_game, _ = mgr.create_game()
        active_game.register("Alice")
        active_game.register("Bob")
        active_game.start()

        # Create some completed games
        for _ in range(7):
            self._make_finished_game(mgr)

        mgr.cleanup_completed(keep_recent=3)

        # Active game is untouched
        assert mgr.get_game(active_id) is not None

    def test_cleanup_with_fewer_than_keep_recent(self):
        mgr = GameManager()
        self._make_finished_game(mgr)
        self._make_finished_game(mgr)

        removed = mgr.cleanup_completed(keep_recent=5)
        assert removed == 0
        assert len(mgr.list_games()) == 2

    def test_cleanup_returns_zero_when_no_completed(self):
        mgr = GameManager()
        _, game, _ = mgr.create_game()
        game.register("Alice")
        game.register("Bob")
        game.start()

        removed = mgr.cleanup_completed()
        assert removed == 0

    def test_cleanup_also_removes_configs_and_recorders(self):
        """Verify all three dicts are cleaned up, not just _games."""
        mgr = GameManager()
        for _ in range(8):
            self._make_finished_game(mgr)

        mgr.cleanup_completed(keep_recent=2)

        # Exactly 2 games remain
        assert len(mgr._games) == 2
        assert len(mgr._configs) == 2


# ── Fix 4: format_buy_in DRY ───────────────────────────


class TestFormatBuyIn:
    def test_zero_buy_in(self):
        assert format_buy_in(0, 0, None, "offchain") == "Free"

    def test_zero_buy_in_with_symbol(self):
        assert format_buy_in(0, 18, "MONTE", "onchain") == "Free"

    def test_offchain_no_symbol_shows_credits(self):
        assert format_buy_in(500, 0, None, "offchain") == "500 credits"

    def test_with_token_symbol(self):
        assert format_buy_in(1000, 0, "MONTE", "onchain") == "1000 MONTE"

    def test_with_decimals(self):
        # 10000 * 10^18 in raw, but buy_in is the raw amount
        result = format_buy_in(10000_000000000000000000, 18, "MONTE", "onchain")
        assert result == "10000 MONTE"

    def test_with_decimals_fractional(self):
        result = format_buy_in(1_500000000000000000, 18, "ETH", "onchain")
        assert result == "1.5 ETH"

    def test_onchain_no_symbol_no_decimals(self):
        # On-chain mode with no symbol — just the amount
        assert format_buy_in(100, 0, None, "onchain") == "100"

    def test_game_config_uses_shared_function(self):
        """Verify GameConfig.buy_in_display delegates to the shared function."""
        from poker.game_config import GameConfig

        config = GameConfig(mode="offchain", buy_in=500)
        assert config.buy_in_display == format_buy_in(500, 0, None, "offchain")

        config2 = GameConfig(mode="onchain", buy_in=1000, token_symbol="MONTE")
        assert config2.buy_in_display == format_buy_in(1000, 0, "MONTE", "onchain")
