"""Integration tests for the dice game API endpoints."""

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
from poker.game import Game
from poker.history_store import HandSummaryStore
from poker.recorder import make_poker_materializer
from poker.router import configure as configure_poker_router
from core.event_bus import GameEventBus
from game_api.ws_router import configure as configure_ws_router


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

    game_module.event_bus = GameEventBus()
    game_module.manager = GameManager(
        recorder_factory=make_recorder,
        metadata_store=game_module.metadata_store,
        event_bus=game_module.event_bus,
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
    configure_ws_router(
        mgr=game_module.manager,
        acc=game_module.account_store,
        bus=game_module.event_bus,
    )
    yield


@pytest.fixture
def client():
    return TestClient(game_module.app)


# ── Helpers ──────────────────────────────────────────────

def auth_header(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def register(username: str) -> str:
    return game_module.account_store.create_account(username)


def create_dice_game(client, **kwargs) -> str:
    body = {"mode": "offchain", **kwargs}
    resp = client.post("/game/dice/games", json=body)
    assert resp.status_code == 200, resp.json()
    data = resp.json()
    assert data["mode"] == "offchain"
    return data["game_id"]


def join_game(client, game_id: str, api_key: str) -> dict:
    resp = client.post(f"/game/dice/{game_id}/join", json={}, headers=auth_header(api_key))
    assert resp.status_code == 200, resp.json()
    return resp.json()


def start_game(client, game_id: str, api_key: str) -> dict:
    resp = client.post(f"/game/dice/{game_id}/start", headers=auth_header(api_key))
    assert resp.status_code == 200, resp.json()
    return resp.json()


# ── Create ───────────────────────────────────────────────

class TestDiceCreate:
    def test_create_dice_game(self, client):
        gid = create_dice_game(client)
        assert isinstance(gid, str) and len(gid) == 32

    def test_onchain_rejected_for_dice(self, client):
        resp = client.post("/game/dice/games", json={
            "mode": "onchain",
            "token": "0x1234567890abcdef1234567890abcdef12345678",
        })
        assert resp.status_code == 400
        assert "not supported" in resp.json()["detail"].lower()


# ── Join / Waiting / Start ───────────────────────────────

class TestDiceJoinStart:
    def test_join(self, client):
        key = register("Alice")
        gid = create_dice_game(client)
        data = join_game(client, gid, key)
        assert data["name"] == "Alice"

    def test_waiting(self, client):
        key = register("Alice")
        gid = create_dice_game(client)
        join_game(client, gid, key)
        resp = client.get(f"/game/dice/{gid}/waiting")
        assert resp.status_code == 200
        assert resp.json()["player_count"] == 1

    def test_start(self, client):
        key_a = register("Alice")
        key_b = register("Bob")
        gid = create_dice_game(client)
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        data = start_game(client, gid, key_a)
        assert data["hand_number"] == 1

    def test_start_requires_player(self, client):
        key_a = register("Alice")
        key_b = register("Bob")
        key_c = register("Charlie")
        gid = create_dice_game(client)
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        resp = client.post(f"/game/dice/{gid}/start", headers=auth_header(key_c))
        assert resp.status_code == 403


# ── State & Action ───────────────────────────────────────

class TestDiceAction:
    def _setup_game(self, client) -> tuple[str, str, str]:
        key_a = register("Alice")
        key_b = register("Bob")
        gid = create_dice_game(client)
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        start_game(client, gid, key_a)
        return gid, key_a, key_b

    def test_state_shows_dice_fields(self, client):
        gid, key_a, _ = self._setup_game(client)
        resp = client.get(f"/game/dice/{gid}/state", headers=auth_header(key_a))
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_type"] == "dice"
        assert data["phase"] == "betting"
        assert data["ante"] == 20
        assert "is_your_turn" in data

    def test_action_high(self, client):
        gid, key_a, _ = self._setup_game(client)
        resp = client.post(
            f"/game/dice/{gid}/action",
            json={"action": "high"},
            headers=auth_header(key_a),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_action_invalid(self, client):
        gid, key_a, _ = self._setup_game(client)
        resp = client.post(
            f"/game/dice/{gid}/action",
            json={"action": "bluff"},
            headers=auth_header(key_a),
        )
        assert resp.status_code == 400

    def test_full_round(self, client):
        gid, key_a, key_b = self._setup_game(client)
        # Alice bets
        client.post(f"/game/dice/{gid}/action", json={"action": "high"}, headers=auth_header(key_a))
        # Bob bets
        client.post(f"/game/dice/{gid}/action", json={"action": "low"}, headers=auth_header(key_b))
        # Round should have resolved
        state = client.get(f"/game/dice/{gid}/state", headers=auth_header(key_a)).json()
        # Either in a new round or game over
        assert state["round_number"] >= 2 or state["game_over"]

    def test_state_version_conflict(self, client):
        gid, key_a, _ = self._setup_game(client)
        resp = client.post(
            f"/game/dice/{gid}/action",
            json={"action": "high", "expected_version": 9999},
            headers=auth_header(key_a),
        )
        assert resp.status_code == 409


# ── Spectator ────────────────────────────────────────────

class TestDiceSpectator:
    def test_spectator(self, client):
        key_a = register("Alice")
        key_b = register("Bob")
        gid = create_dice_game(client)
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        start_game(client, gid, key_a)

        resp = client.get(f"/game/dice/{gid}/spectator")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_type"] == "dice"
        assert data["started"] is True
        assert len(data["players"]) == 2


# ── Resign ───────────────────────────────────────────────

class TestDiceResignAPI:
    def test_resign(self, client):
        key_a = register("Alice")
        key_b = register("Bob")
        gid = create_dice_game(client)
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        start_game(client, gid, key_a)

        resp = client.post(f"/game/dice/{gid}/resign", headers=auth_header(key_b))
        assert resp.status_code == 200

        state = client.get(f"/game/dice/{gid}/state", headers=auth_header(key_a)).json()
        assert state["game_over"] is True
        assert state["winner"] == "Alice"


# ── Chat ─────────────────────────────────────────────────

class TestDiceChat:
    def test_chat(self, client):
        key_a = register("Alice")
        key_b = register("Bob")
        gid = create_dice_game(client)
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)

        resp = client.post(
            f"/game/dice/{gid}/chat",
            json={"message": "Good luck!"},
            headers=auth_header(key_a),
        )
        assert resp.status_code == 200


# ── Cross-game isolation ─────────────────────────────────

class TestCrossGameIsolation:
    def test_poker_routes_reject_dice_game(self, client):
        key = register("Alice")
        gid = create_dice_game(client)
        join_game(client, gid, key)
        # Try accessing dice game via poker endpoint
        resp = client.get(f"/game/poker/{gid}/waiting")
        assert resp.status_code == 404

    def test_dice_routes_reject_poker_game(self, client):
        key = register("Alice")
        resp = client.post("/game/poker/games", json={"mode": "offchain"})
        gid = resp.json()["game_id"]
        # Try accessing poker game via dice endpoint
        resp = client.get(f"/game/dice/{gid}/waiting")
        assert resp.status_code == 404

    def test_both_game_types_in_lobby(self, client):
        """Both poker and dice games appear in the lobby with correct game_type."""
        client.post("/game/poker/games", json={"mode": "offchain"})
        client.post("/game/dice/games", json={"mode": "offchain"})
        # Check lobby via data API is beyond scope; verify manager has both
        summaries = game_module.manager.list_games()
        types = {s.game_type for s in summaries}
        assert types == {"poker", "dice"}
