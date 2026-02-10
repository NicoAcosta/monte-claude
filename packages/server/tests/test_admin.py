"""Tests for admin game control endpoints."""

import pytest
from fastapi.testclient import TestClient

import game_api.app as game_module
from core.account_store import AccountStore
from core.balance_store import BalanceStore
from core.db import get_pool
from core.game_manager import GameManager
from core.game_metadata_store import GameMetadataStore
from core.game_recorder import GameRecorder
from core.round_summary_store import RoundSummaryStore
from core.stream_store import StreamStore
from core.history_store import GameEventStore, PlayerStatsStore
from dice.game import DiceGame
from dice.recorder import make_dice_materializer
from dice.router import configure as configure_dice_router
from game_api.admin_router import configure as configure_admin_router
from poker.game import Game
from poker.history_store import HandSummaryStore
from poker.recorder import make_poker_materializer
from poker.router import configure as configure_poker_router

TEST_ADMIN_KEY = "test-admin-key-12345"


@pytest.fixture(autouse=True)
def reset_state():
    pool = get_pool()
    game_module.event_store = GameEventStore(pool)
    game_module.summary_store = HandSummaryStore(pool)
    game_module.stats_store = PlayerStatsStore(pool)
    game_module.metadata_store = GameMetadataStore(pool)
    game_module.stream_store = StreamStore(pool)
    game_module.round_summary_store = RoundSummaryStore(pool)

    poker_materializer = make_poker_materializer(game_module.summary_store)
    dice_materializer = make_dice_materializer(game_module.round_summary_store)

    def make_recorder(game_id: str, game_type: str = "poker") -> GameRecorder:
        mat = poker_materializer if game_type == "poker" else dice_materializer
        return GameRecorder(
            game_id,
            game_module.event_store,
            game_module.stats_store,
            summary_materializer=mat,
        )

    game_module.manager = GameManager(
        recorder_factory=make_recorder,
        metadata_store=game_module.metadata_store,
    )
    game_module.manager.register_game_type("poker", Game)
    game_module.manager.register_game_type("dice", DiceGame)

    game_module.account_store = AccountStore(pool)
    game_module.balance_store = BalanceStore(pool)

    configure_poker_router(
        mgr=game_module.manager,
        bal=game_module.balance_store,
        acc=game_module.account_store,
        meta=game_module.metadata_store,
        esc_audit=game_module.escrow_audit,
        auth_dep=game_module.require_auth,
    )
    configure_dice_router(
        mgr=game_module.manager,
        bal=game_module.balance_store,
        acc=game_module.account_store,
        meta=game_module.metadata_store,
        auth_dep=game_module.require_auth,
    )
    configure_admin_router(
        mgr=game_module.manager,
        admin_keys=frozenset({TEST_ADMIN_KEY}),
    )
    yield


@pytest.fixture
def client():
    return TestClient(game_module.app)


def auth_header(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def admin_header(key: str = TEST_ADMIN_KEY) -> dict[str, str]:
    return {"X-Admin-Key": key}


def register(username: str) -> str:
    return game_module.account_store.create_account(username)


# ── Admin auth ─────────────────────────────────────────


class TestAdminAuth:
    def test_status_requires_admin_key(self, client):
        resp = client.get("/admin/status")
        assert resp.status_code == 403

    def test_status_rejects_invalid_key(self, client):
        resp = client.get("/admin/status", headers={"X-Admin-Key": "wrong-key"})
        assert resp.status_code == 403

    def test_disable_requires_admin_key(self, client):
        resp = client.post("/admin/games/poker/disable")
        assert resp.status_code == 403

    def test_enable_requires_admin_key(self, client):
        resp = client.post("/admin/games/poker/enable")
        assert resp.status_code == 403

    def test_status_accepts_valid_key(self, client):
        resp = client.get("/admin/status", headers=admin_header())
        assert resp.status_code == 200

    def test_returns_403_when_no_keys_configured(self, client):
        """If ADMIN_API_KEYS is empty, all admin endpoints are locked."""
        configure_admin_router(
            mgr=game_module.manager,
            admin_keys=frozenset(),
        )
        resp = client.get("/admin/status", headers=admin_header())
        assert resp.status_code == 403
        assert "not configured" in resp.json()["detail"].lower()


# ── Public game types endpoint ──────────────────────────


class TestPublicGameTypes:
    def test_game_types_returns_all(self, client):
        resp = client.get("/game/types")
        assert resp.status_code == 200
        assert resp.json() == {"poker": True, "dice": True}

    def test_game_types_reflects_disable(self, client):
        client.post("/admin/games/poker/disable", headers=admin_header())
        resp = client.get("/game/types")
        assert resp.status_code == 200
        assert resp.json() == {"poker": False, "dice": True}

    def test_game_types_reflects_re_enable(self, client):
        client.post("/admin/games/poker/disable", headers=admin_header())
        client.post("/admin/games/poker/enable", headers=admin_header())
        resp = client.get("/game/types")
        assert resp.status_code == 200
        assert resp.json() == {"poker": True, "dice": True}


# ── Admin status ────────────────────────────────────────


class TestAdminStatus:
    def test_status_returns_all_game_types(self, client):
        resp = client.get("/admin/status", headers=admin_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_types"] == {"poker": True, "dice": True}


# ── Enable / disable ────────────────────────────────────


class TestAdminDisable:
    def test_disable_poker(self, client):
        resp = client.post("/admin/games/poker/disable", headers=admin_header())
        assert resp.status_code == 200
        assert resp.json()["game_types"]["poker"] is False
        assert resp.json()["game_types"]["dice"] is True

    def test_enable_poker_after_disable(self, client):
        client.post("/admin/games/poker/disable", headers=admin_header())
        resp = client.post("/admin/games/poker/enable", headers=admin_header())
        assert resp.status_code == 200
        assert resp.json()["game_types"]["poker"] is True

    def test_disable_unknown_type_returns_404(self, client):
        resp = client.post("/admin/games/unknown/disable", headers=admin_header())
        assert resp.status_code == 404

    def test_enable_unknown_type_returns_404(self, client):
        resp = client.post("/admin/games/unknown/enable", headers=admin_header())
        assert resp.status_code == 404


# ── Downstream effects ──────────────────────────────────


class TestDisabledGameCreation:
    def test_disabled_type_rejects_new_game(self, client):
        client.post("/admin/games/poker/disable", headers=admin_header())
        resp = client.post(
            "/game/poker/games",
            json={"max_players": 2, "buy_in": 0, "mode": "offchain"},
        )
        assert resp.status_code == 400
        assert "disabled" in resp.json()["detail"].lower()

    def test_disabled_poker_does_not_affect_dice(self, client):
        client.post("/admin/games/poker/disable", headers=admin_header())
        key = register("alice")
        resp = client.post(
            "/game/dice/games",
            json={"max_players": 2, "buy_in": 0, "mode": "offchain"},
            headers=auth_header(key),
        )
        assert resp.status_code == 200

    def test_existing_game_still_playable_after_disable(self, client):
        """Disabling a game type does NOT kill existing games."""
        key_a = register("alice")
        key_b = register("bob")

        # Create and join a poker game while enabled
        resp = client.post(
            "/game/poker/games",
            json={"max_players": 2, "buy_in": 0, "mode": "offchain"},
        )
        game_id = resp.json()["game_id"]
        client.post(
            f"/game/poker/{game_id}/join",
            json={"player_name": "alice"},
            headers=auth_header(key_a),
        )
        client.post(
            f"/game/poker/{game_id}/join",
            json={"player_name": "bob"},
            headers=auth_header(key_b),
        )

        # Disable poker
        client.post("/admin/games/poker/disable", headers=admin_header())

        # Existing game still works: start, get state, do actions
        resp = client.post(
            f"/game/poker/{game_id}/start",
            headers=auth_header(key_a),
        )
        assert resp.status_code == 200

        resp = client.get(
            f"/game/poker/{game_id}/state",
            headers=auth_header(key_a),
        )
        assert resp.status_code == 200
