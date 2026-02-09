import pytest
from datetime import datetime, timedelta, timezone

from poker.balance_store import BalanceStore, FAUCET_COOLDOWN_SECONDS
from poker.db import get_pool


@pytest.fixture
def store():
    return BalanceStore(get_pool())


class TestGet:
    def test_unknown_user_returns_zero(self, store):
        bal = store.get("alice")
        assert bal.username == "alice"
        assert bal.amount == 0
        assert bal.last_claim_at == ""

    def test_returns_stored_balance(self, store, make_account):
        make_account("alice")
        store.credit("alice", 500)
        bal = store.get("alice")
        assert bal.amount == 500


class TestCredit:
    def test_credit_increases_balance(self, store, make_account):
        make_account("alice")
        bal = store.credit("alice", 100)
        assert bal.amount == 100

    def test_credit_stacks(self, store, make_account):
        make_account("alice")
        store.credit("alice", 100)
        bal = store.credit("alice", 200)
        assert bal.amount == 300

    def test_credit_zero_is_noop(self, store, make_account):
        make_account("alice")
        store.credit("alice", 100)
        bal = store.credit("alice", 0)
        assert bal.amount == 100

    def test_credit_negative_raises(self, store):
        with pytest.raises(ValueError, match="non-negative"):
            store.credit("alice", -1)


class TestDebit:
    def test_debit_decreases_balance(self, store, make_account):
        make_account("alice")
        store.credit("alice", 500)
        bal = store.debit("alice", 200)
        assert bal.amount == 300

    def test_debit_exact_balance(self, store, make_account):
        make_account("alice")
        store.credit("alice", 100)
        bal = store.debit("alice", 100)
        assert bal.amount == 0

    def test_debit_insufficient_raises(self, store, make_account):
        make_account("alice")
        store.credit("alice", 50)
        with pytest.raises(ValueError, match="Insufficient balance"):
            store.debit("alice", 100)

    def test_debit_zero_balance_raises(self, store):
        with pytest.raises(ValueError, match="Insufficient balance"):
            store.debit("alice", 1)

    def test_debit_negative_raises(self, store):
        with pytest.raises(ValueError, match="non-negative"):
            store.debit("alice", -1)

    def test_debit_zero_nonexistent_user_raises(self, store):
        """CR-4: debit(0) for a non-existent user must raise ValueError, not TypeError."""
        with pytest.raises(ValueError, match="Insufficient balance"):
            store.debit("nonexistent", 0)


class TestFaucet:
    def test_first_claim_succeeds(self, store, make_account):
        make_account("alice")
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        bal = store.try_claim_faucet("alice", 1000, now=now)
        assert bal.amount == 1000
        assert bal.last_claim_at == now.isoformat()

    def test_second_claim_within_24h_raises(self, store, make_account):
        make_account("alice")
        t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        store.try_claim_faucet("alice", 1000, now=t0)

        t1 = t0 + timedelta(hours=12)
        with pytest.raises(ValueError, match="cooldown"):
            store.try_claim_faucet("alice", 1000, now=t1)

    def test_claim_after_24h_succeeds(self, store, make_account):
        make_account("alice")
        t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        store.try_claim_faucet("alice", 1000, now=t0)

        t1 = t0 + timedelta(seconds=FAUCET_COOLDOWN_SECONDS)
        bal = store.try_claim_faucet("alice", 1000, now=t1)
        assert bal.amount == 2000

    def test_faucet_stacks_with_existing_balance(self, store, make_account):
        make_account("alice")
        store.credit("alice", 500)
        bal = store.try_claim_faucet("alice", 1000)
        assert bal.amount == 1500

    def test_preserves_last_claim_on_credit_debit(self, store, make_account):
        make_account("alice")
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        store.try_claim_faucet("alice", 1000, now=now)
        store.credit("alice", 100)
        bal = store.debit("alice", 50)
        assert bal.last_claim_at == now.isoformat()


class TestPersistence:
    def test_data_persists_across_instances(self, make_account):
        make_account("alice")
        make_account("bob")
        pool = get_pool()
        store1 = BalanceStore(pool)
        store1.credit("alice", 500)
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        store1.try_claim_faucet("bob", 1000, now=now)

        # New store instance reads from same pool
        store2 = BalanceStore(pool)
        assert store2.get("alice").amount == 500
        assert store2.get("bob").amount == 1000
        assert store2.get("bob").last_claim_at == now.isoformat()

    def test_unknown_user_not_persisted(self):
        pool = get_pool()
        store1 = BalanceStore(pool)
        store1.get("alice")  # just reading, no mutation

        store2 = BalanceStore(pool)
        # Should still be zero (not persisted)
        assert store2.get("alice").amount == 0


class TestBalanceHistory:
    """Verify balance_history rows are created on mutations."""

    def test_credit_creates_history(self, store, make_account):
        make_account("alice")
        store.credit("alice", 100, reason="test_credit")
        pool = get_pool()
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT username, amount, balance_after, reason FROM balance_history WHERE username = %s",
                ("alice",),
            ).fetchall()
        assert len(rows) == 1
        assert rows[0] == ("alice", 100, 100, "test_credit")

    def test_debit_creates_history(self, store, make_account):
        make_account("alice")
        store.credit("alice", 500)
        store.debit("alice", 200, reason="test_debit")
        pool = get_pool()
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT amount, balance_after, reason FROM balance_history WHERE username = %s ORDER BY id",
                ("alice",),
            ).fetchall()
        assert len(rows) == 2
        assert rows[1] == (-200, 300, "test_debit")

    def test_faucet_creates_history(self, store, make_account):
        make_account("alice")
        store.try_claim_faucet("alice", 1000)
        pool = get_pool()
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT amount, balance_after, reason FROM balance_history WHERE username = %s",
                ("alice",),
            ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (1000, 1000, "faucet")
