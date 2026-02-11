"""Tests for bug report and question submission endpoints."""

import pytest
from fastapi.testclient import TestClient

import account_api.app as account_module
from core.account_store import AccountStore
from core.audit import AuthAuditStore
from core.balance_store import BalanceStore
from core.feedback_store import FeedbackStore
from core.db import get_pool


@pytest.fixture(autouse=True)
def reset_state():
    """Reset Account API stores before each test."""
    pool = get_pool()
    account_module.account_store = AccountStore(pool)
    account_module.balance_store = BalanceStore(pool)
    account_module.auth_audit = AuthAuditStore(pool)
    account_module.feedback_store = FeedbackStore(pool)
    account_module._register_limiter.clear()
    account_module._faucet_limiter.clear()
    account_module._bug_limiter.clear()
    account_module._question_limiter.clear()
    yield


@pytest.fixture
def client():
    return TestClient(account_module.app)


# ── Helpers ──────────────────────────────────────────────

def auth_header(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def register(client, username: str) -> str:
    resp = client.post("/api/accounts/register", json={"username": username})
    assert resp.status_code == 200
    return resp.json()["api_key"]


# ── Bug Reports ─────────────────────────────────────────

class TestBugReport:
    def test_requires_auth(self, client):
        resp = client.post("/api/accounts/bug", json={"body": "Something broke badly"})
        assert resp.status_code == 401

    def test_success(self, client):
        key = register(client, "Alice")
        resp = client.post(
            "/api/accounts/bug",
            json={"body": "The fold button doesn't work"},
            headers=auth_header(key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["remaining"] == 4  # 5 max - 1 used

    def test_body_too_short(self, client):
        key = register(client, "Alice")
        resp = client.post(
            "/api/accounts/bug",
            json={"body": "short"},
            headers=auth_header(key),
        )
        assert resp.status_code == 422

    def test_body_too_long(self, client):
        key = register(client, "Alice")
        resp = client.post(
            "/api/accounts/bug",
            json={"body": "x" * 2001},
            headers=auth_header(key),
        )
        assert resp.status_code == 422

    def test_rate_limit(self, client):
        key = register(client, "Alice")
        for i in range(5):
            resp = client.post(
                "/api/accounts/bug",
                json={"body": f"Bug report number {i} with enough length"},
                headers=auth_header(key),
            )
            assert resp.status_code == 200
            assert resp.json()["remaining"] == 4 - i
        # 6th should be rate-limited
        resp = client.post(
            "/api/accounts/bug",
            json={"body": "One more bug report attempt"},
            headers=auth_header(key),
        )
        assert resp.status_code == 429
        assert "rate limit" in resp.json()["detail"].lower()

    def test_per_user_isolation(self, client):
        key_a = register(client, "Alice")
        key_b = register(client, "Bob")
        # Exhaust Alice's quota
        for i in range(5):
            client.post(
                "/api/accounts/bug",
                json={"body": f"Alice bug report {i} with enough text"},
                headers=auth_header(key_a),
            )
        # Bob should still be able to submit
        resp = client.post(
            "/api/accounts/bug",
            json={"body": "Bob's bug report is fine"},
            headers=auth_header(key_b),
        )
        assert resp.status_code == 200
        assert resp.json()["remaining"] == 4

    def test_db_persistence(self, client):
        key = register(client, "Alice")
        body = "The raise amount is calculated wrong"
        client.post("/api/accounts/bug", json={"body": body}, headers=auth_header(key))

        pool = get_pool()
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT username, body FROM bug_reports WHERE username = %s",
                ("Alice",),
            ).fetchone()
        assert row is not None
        assert row[0] == "Alice"
        assert row[1] == body


# ── Questions ───────────────────────────────────────────

class TestQuestion:
    def test_requires_auth(self, client):
        resp = client.post("/api/accounts/question", json={"body": "How do I raise properly?"})
        assert resp.status_code == 401

    def test_success(self, client):
        key = register(client, "Alice")
        resp = client.post(
            "/api/accounts/question",
            json={"body": "How does the timer extension work?"},
            headers=auth_header(key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["remaining"] == 9  # 10 max - 1 used

    def test_body_too_short(self, client):
        key = register(client, "Alice")
        resp = client.post(
            "/api/accounts/question",
            json={"body": "how?"},
            headers=auth_header(key),
        )
        assert resp.status_code == 422

    def test_body_too_long(self, client):
        key = register(client, "Alice")
        resp = client.post(
            "/api/accounts/question",
            json={"body": "q" * 2001},
            headers=auth_header(key),
        )
        assert resp.status_code == 422

    def test_rate_limit(self, client):
        key = register(client, "Alice")
        for i in range(10):
            resp = client.post(
                "/api/accounts/question",
                json={"body": f"Question number {i} with enough text here"},
                headers=auth_header(key),
            )
            assert resp.status_code == 200
            assert resp.json()["remaining"] == 9 - i
        # 11th should be rate-limited
        resp = client.post(
            "/api/accounts/question",
            json={"body": "One more question attempt here"},
            headers=auth_header(key),
        )
        assert resp.status_code == 429
        assert "rate limit" in resp.json()["detail"].lower()

    def test_per_user_isolation(self, client):
        key_a = register(client, "Alice")
        key_b = register(client, "Bob")
        # Exhaust Alice's quota
        for i in range(10):
            client.post(
                "/api/accounts/question",
                json={"body": f"Alice question {i} with enough length"},
                headers=auth_header(key_a),
            )
        # Bob should still be able to submit
        resp = client.post(
            "/api/accounts/question",
            json={"body": "Bob's question should work fine"},
            headers=auth_header(key_b),
        )
        assert resp.status_code == 200
        assert resp.json()["remaining"] == 9

    def test_db_persistence(self, client):
        key = register(client, "Alice")
        body = "What happens when the timer runs out?"
        client.post("/api/accounts/question", json={"body": body}, headers=auth_header(key))

        pool = get_pool()
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT username, body FROM questions WHERE username = %s",
                ("Alice",),
            ).fetchone()
        assert row is not None
        assert row[0] == "Alice"
        assert row[1] == body
