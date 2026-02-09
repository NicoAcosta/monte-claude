import pytest
from core.account_store import AccountStore, KEY_PREFIX, hash_key
from core.db import get_pool


@pytest.fixture
def store():
    return AccountStore(get_pool())


class TestCreateAccount:
    def test_create_returns_key_with_prefix(self, store):
        key = store.create_account("Alice")
        assert key.startswith(KEY_PREFIX)
        assert len(key) > 40

    def test_create_stores_account(self, store):
        store.create_account("Alice")
        acct = store.get_account("Alice")
        assert acct is not None
        assert acct.username == "Alice"

    def test_duplicate_username_rejected(self, store):
        store.create_account("Alice")
        with pytest.raises(ValueError, match="already taken"):
            store.create_account("Alice")

    def test_empty_username_rejected(self, store):
        with pytest.raises(ValueError, match="empty"):
            store.create_account("")

    def test_whitespace_username_rejected(self, store):
        with pytest.raises(ValueError, match="empty"):
            store.create_account("   ")


class TestVerifyKey:
    def test_verify_valid_key(self, store):
        key = store.create_account("Alice")
        acct = store.verify_key(key)
        assert acct is not None
        assert acct.username == "Alice"

    def test_verify_invalid_key(self, store):
        store.create_account("Alice")
        assert store.verify_key("pk_bogus") is None

    def test_verify_empty_key(self, store):
        assert store.verify_key("") is None


class TestPersistence:
    def test_data_persists_across_instances(self):
        pool = get_pool()
        store1 = AccountStore(pool)
        key = store1.create_account("Alice")

        # New store instance reads from same pool
        store2 = AccountStore(pool)
        acct = store2.verify_key(key)
        assert acct is not None
        assert acct.username == "Alice"

    def test_multiple_accounts_persist(self):
        pool = get_pool()
        store1 = AccountStore(pool)
        key_a = store1.create_account("Alice")
        key_b = store1.create_account("Bob")

        store2 = AccountStore(pool)
        assert store2.verify_key(key_a).username == "Alice"
        assert store2.verify_key(key_b).username == "Bob"


class TestHashKey:
    def test_deterministic(self):
        assert hash_key("test") == hash_key("test")

    def test_different_inputs_different_hashes(self):
        assert hash_key("a") != hash_key("b")

    def test_stored_hash_not_plaintext(self, store):
        key = store.create_account("Alice")
        acct = store.get_account("Alice")
        assert acct.key_hash != key
        assert acct.key_hash == hash_key(key)
