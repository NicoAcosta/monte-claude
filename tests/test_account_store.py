import pytest
from poker.account_store import AccountStore, KEY_PREFIX, hash_key


@pytest.fixture
def store(tmp_path):
    return AccountStore(tmp_path / "accounts.csv")


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
    def test_reload_from_csv(self, tmp_path):
        csv_path = tmp_path / "accounts.csv"
        store1 = AccountStore(csv_path)
        key = store1.create_account("Alice")

        # New store instance reads from same CSV
        store2 = AccountStore(csv_path)
        acct = store2.verify_key(key)
        assert acct is not None
        assert acct.username == "Alice"

    def test_csv_created_on_init(self, tmp_path):
        csv_path = tmp_path / "data" / "accounts.csv"
        AccountStore(csv_path)
        assert csv_path.exists()

    def test_multiple_accounts_persist(self, tmp_path):
        csv_path = tmp_path / "accounts.csv"
        store1 = AccountStore(csv_path)
        key_a = store1.create_account("Alice")
        key_b = store1.create_account("Bob")

        store2 = AccountStore(csv_path)
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
