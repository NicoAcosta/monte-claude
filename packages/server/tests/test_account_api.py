"""Tests for the Account API — registration, faucet, balance."""

import pytest
from fastapi.testclient import TestClient

import account_api.app as account_module
from core.account_store import AccountStore
from core.audit import AuthAuditStore
from core.balance_store import BalanceStore
from core.db import get_pool


@pytest.fixture(autouse=True)
def reset_state():
    """Reset Account API stores before each test."""
    pool = get_pool()
    account_module.account_store = AccountStore(pool)
    account_module.balance_store = BalanceStore(pool)
    account_module.auth_audit = AuthAuditStore(pool)
    account_module._register_limiter.clear()
    account_module._faucet_limiter.clear()
    yield


@pytest.fixture
def client():
    return TestClient(account_module.app)


# ── Helpers ──────────────────────────────────────────────

def auth_header(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def register(client, username: str) -> str:
    resp = client.post("/api/register", json={"username": username})
    assert resp.status_code == 200
    return resp.json()["api_key"]


# ── Registration ─────────────────────────────────────────

class TestRegistration:
    def test_register_success(self, client):
        resp = client.post("/api/register", json={"username": "Alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "Alice"
        assert data["api_key"].startswith("pk_")

    def test_register_duplicate(self, client):
        register(client, "Alice")
        resp = client.post("/api/register", json={"username": "Alice"})
        assert resp.status_code == 400

    def test_register_empty_username(self, client):
        resp = client.post("/api/register", json={"username": ""})
        assert resp.status_code == 400

    def test_register_rate_limit(self, client):
        """Temporarily tighten the limiter to verify rate limiting works."""
        from core.rate_limit import RateLimitConfig, RateLimiter
        original = account_module._register_limiter
        account_module._register_limiter = RateLimiter(RateLimitConfig(max_requests=2, window_seconds=3600))
        try:
            for i in range(2):
                resp = client.post("/api/register", json={"username": f"user{i}"})
                assert resp.status_code == 200
            # 3rd should be rate-limited
            resp = client.post("/api/register", json={"username": "user2"})
            assert resp.status_code == 429
            assert "rate limit" in resp.json()["detail"].lower()
        finally:
            account_module._register_limiter = original


# ── Faucet ───────────────────────────────────────────────

class TestFaucet:
    def test_faucet_requires_auth(self, client):
        resp = client.post("/api/faucet")
        assert resp.status_code == 401

    def test_faucet_success(self, client):
        key = register(client, "Alice")
        resp = client.post("/api/faucet", headers=auth_header(key))
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["new_balance"] == 10_000
        assert data["next_claim_at"]

    def test_faucet_cooldown(self, client):
        key = register(client, "Alice")
        client.post("/api/faucet", headers=auth_header(key))
        resp = client.post("/api/faucet", headers=auth_header(key))
        assert resp.status_code == 429
        assert "cooldown" in resp.json()["detail"].lower()


# ── Balance ──────────────────────────────────────────────

class TestBalance:
    def test_balance_requires_auth(self, client):
        resp = client.get("/api/balance")
        assert resp.status_code == 401

    def test_balance_after_faucet(self, client):
        key = register(client, "Alice")
        client.post("/api/faucet", headers=auth_header(key))
        resp = client.get("/api/balance", headers=auth_header(key))
        assert resp.status_code == 200
        assert resp.json()["balance"] == 10_000

    def test_balance_zero_default(self, client):
        key = register(client, "Alice")
        resp = client.get("/api/balance", headers=auth_header(key))
        assert resp.status_code == 200
        assert resp.json()["balance"] == 0


# ── Health ───────────────────────────────────────────────

class TestHealth:
    def test_ping(self, client):
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
