"""Integration tests for the off-chain bankroll system."""
import pytest
from fastapi.testclient import TestClient

import poker.server as server_module
from poker.account_store import AccountStore
from poker.balance_store import BalanceStore
from poker.db import get_pool
from poker.game_manager import GameManager
from poker.game_recorder import GameRecorder
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore
from poker.stream_manager import StreamManager


@pytest.fixture(autouse=True)
def reset_state():
    pool = get_pool()
    server_module.event_store = GameEventStore(pool)
    server_module.summary_store = HandSummaryStore(pool)
    server_module.stats_store = PlayerStatsStore(pool)

    def make_recorder(game_id: int) -> GameRecorder:
        return GameRecorder(
            game_id,
            server_module.event_store,
            server_module.summary_store,
            server_module.stats_store,
        )

    server_module.manager = GameManager(recorder_factory=make_recorder)
    server_module.account_store = AccountStore(pool)
    server_module.balance_store = BalanceStore(pool)
    server_module.stream_manager = StreamManager()
    yield


@pytest.fixture
def client():
    return TestClient(server_module.app)


# ── Helpers ──────────────────────────────────────────────

def auth_header(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def register(client, username: str) -> str:
    resp = client.post("/api/register", json={"username": username})
    assert resp.status_code == 200
    return resp.json()["api_key"]


def claim_faucet(client, api_key: str) -> dict:
    resp = client.post("/api/faucet", headers=auth_header(api_key))
    assert resp.status_code == 200
    return resp.json()


def get_balance(client, api_key: str) -> int:
    resp = client.get("/api/balance", headers=auth_header(api_key))
    assert resp.status_code == 200
    return resp.json()["balance"]


def create_offchain_game(client, buy_in: int, max_players: int = 0) -> int:
    resp = client.post("/api/games", json={"buy_in": buy_in, "max_players": max_players})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "offchain"
    return data["game_id"]


def join_game(client, game_id: int, api_key: str) -> dict:
    resp = client.post(f"/game/{game_id}/join", json={}, headers=auth_header(api_key))
    assert resp.status_code == 200
    return resp.json()


def start_game(client, game_id: int, api_key: str) -> dict:
    resp = client.post(f"/game/{game_id}/start", headers=auth_header(api_key))
    assert resp.status_code == 200
    return resp.json()


# ── Mode inference tests ─────────────────────────────────

class TestModeInference:
    def test_no_token_is_offchain(self, client):
        resp = client.post("/api/games", json={"buy_in": 100})
        assert resp.status_code == 200
        assert resp.json()["mode"] == "offchain"

    def test_with_token_is_onchain(self, client):
        resp = client.post("/api/games", json={
            "buy_in": 100,
            "token": "0x1234567890abcdef1234567890abcdef12345678",
            "max_players": 2,
        })
        assert resp.status_code == 200
        assert resp.json()["mode"] == "onchain"

    def test_explicit_offchain_mode(self, client):
        resp = client.post("/api/games", json={"buy_in": 100, "mode": "offchain"})
        assert resp.status_code == 200
        assert resp.json()["mode"] == "offchain"

    def test_onchain_without_token_rejected(self, client):
        resp = client.post("/api/games", json={"buy_in": 100, "mode": "onchain"})
        assert resp.status_code == 400
        assert "token" in resp.json()["detail"].lower()

    def test_mode_in_game_list(self, client):
        create_offchain_game(client, buy_in=100)
        resp = client.get("/api/games")
        assert resp.status_code == 200
        games = resp.json()["games"]
        assert len(games) == 1
        assert games[0]["mode"] == "offchain"


# ── Faucet tests ─────────────────────────────────────────

class TestFaucet:
    def test_claim_faucet(self, client):
        key = register(client, "Alice")
        data = claim_faucet(client, key)
        assert data["success"] is True
        assert data["new_balance"] == 10_000
        assert data["next_claim_at"]  # non-empty ISO string

    def test_balance_starts_at_zero(self, client):
        key = register(client, "Alice")
        assert get_balance(client, key) == 0

    def test_faucet_increases_balance(self, client):
        key = register(client, "Alice")
        claim_faucet(client, key)
        assert get_balance(client, key) == 10_000

    def test_double_claim_rejected(self, client):
        key = register(client, "Alice")
        claim_faucet(client, key)
        resp = client.post("/api/faucet", headers=auth_header(key))
        assert resp.status_code == 429
        assert "cooldown" in resp.json()["detail"].lower()


# ── Join debit/refund tests ──────────────────────────────

class TestJoinDebit:
    def test_join_debits_balance(self, client):
        key = register(client, "Alice")
        claim_faucet(client, key)
        gid = create_offchain_game(client, buy_in=500)
        join_game(client, gid, key)
        assert get_balance(client, key) == 9_500

    def test_insufficient_balance_rejected(self, client):
        key = register(client, "Alice")
        # No faucet claim, balance is 0
        gid = create_offchain_game(client, buy_in=500)
        resp = client.post(f"/game/{gid}/join", json={}, headers=auth_header(key))
        assert resp.status_code == 400
        assert "insufficient" in resp.json()["detail"].lower()

    def test_join_failure_refunds(self, client):
        key_alice = register(client, "Alice")
        claim_faucet(client, key_alice)
        gid = create_offchain_game(client, buy_in=500)
        join_game(client, gid, key_alice)
        # Try joining again — name already taken
        resp = client.post(f"/game/{gid}/join", json={}, headers=auth_header(key_alice))
        assert resp.status_code == 400
        # Balance should be refunded (only one debit stuck)
        assert get_balance(client, key_alice) == 9_500

    def test_offchain_join_no_wallet_required(self, client):
        key = register(client, "Alice")
        claim_faucet(client, key)
        gid = create_offchain_game(client, buy_in=100)
        # Omit wallet_address — should work for offchain
        resp = client.post(f"/game/{gid}/join", json={}, headers=auth_header(key))
        assert resp.status_code == 200

    def test_zero_buyin_offchain_no_debit(self, client):
        key = register(client, "Alice")
        gid = create_offchain_game(client, buy_in=0)
        join_game(client, gid, key)
        assert get_balance(client, key) == 0  # still zero, no debit


# ── Start game tests ─────────────────────────────────────

class TestOffchainStart:
    def test_offchain_start_sets_funded(self, client):
        key_a = register(client, "Alice")
        key_b = register(client, "Bob")
        claim_faucet(client, key_a)
        claim_faucet(client, key_b)
        gid = create_offchain_game(client, buy_in=500)
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        start_game(client, gid, key_a)
        # Game started without needing escrow funding
        resp = client.get(f"/game/{gid}/waiting")
        assert resp.json()["started"] is True


# ── Escrow guard tests ───────────────────────────────────

class TestEscrowGuards:
    def test_escrow_rejected_for_offchain(self, client):
        key_a = register(client, "Alice")
        key_b = register(client, "Bob")
        claim_faucet(client, key_a)
        claim_faucet(client, key_b)
        gid = create_offchain_game(client, buy_in=500, max_players=2)
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        resp = client.get(f"/game/{gid}/escrow")
        assert resp.status_code == 400
        assert "on-chain" in resp.json()["detail"].lower()

    def test_funding_rejected_for_offchain(self, client):
        gid = create_offchain_game(client, buy_in=500)
        resp = client.get(f"/game/{gid}/funding")
        assert resp.status_code == 400

    def test_settlement_rejected_for_offchain(self, client):
        gid = create_offchain_game(client, buy_in=500)
        resp = client.get(f"/game/{gid}/settlement")
        assert resp.status_code == 400


# ── Full lifecycle test ──────────────────────────────────

class TestOffchainLifecycle:
    def test_full_game_with_settlement(self, client):
        """Faucet → create → join → play → game_over → settlement credits balance."""
        key_a = register(client, "Alice")
        key_b = register(client, "Bob")
        claim_faucet(client, key_a)
        claim_faucet(client, key_b)

        buy_in = 1000
        gid = create_offchain_game(client, buy_in=buy_in)
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)

        assert get_balance(client, key_a) == 9_000
        assert get_balance(client, key_b) == 9_000

        start_game(client, gid, key_a)

        # Bob resigns immediately — quickest path to game_over
        resp = client.post(f"/game/{gid}/resign", headers=auth_header(key_b))
        assert resp.status_code == 200

        # Trigger settlement via reading state
        state_data = client.get(f"/game/{gid}/state", headers=auth_header(key_a)).json()
        assert state_data["game_over"] is True

        # Verify game is over
        spectator_resp = client.get(f"/game/{gid}/spectator")
        assert spectator_resp.json()["game_over"] is True

        # Check offchain settlement endpoint
        settlement_resp = client.get(f"/game/{gid}/offchain-settlement")
        assert settlement_resp.status_code == 200
        payouts = settlement_resp.json()["payouts"]
        total_payout = sum(p["amount"] for p in payouts)
        assert total_payout == buy_in * 2  # total deposits returned

        # Balances should be updated
        bal_a = get_balance(client, key_a)
        bal_b = get_balance(client, key_b)
        # Sum of (starting faucet - buy_in + payout) should equal 2 * faucet
        assert bal_a + bal_b == 2 * 10_000


class TestOffchainSettlementEndpoint:
    def test_not_offchain_rejected(self, client):
        resp = client.post("/api/games", json={
            "buy_in": 100,
            "token": "0x1234567890abcdef1234567890abcdef12345678",
            "max_players": 2,
        })
        gid = resp.json()["game_id"]
        resp = client.get(f"/game/{gid}/offchain-settlement")
        assert resp.status_code == 400

    def test_game_not_over_rejected(self, client):
        gid = create_offchain_game(client, buy_in=100)
        resp = client.get(f"/game/{gid}/offchain-settlement")
        assert resp.status_code == 400
        assert "not over" in resp.json()["detail"].lower()
