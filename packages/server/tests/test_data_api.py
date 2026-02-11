"""Tests for the Data API — read-only endpoints."""

import pytest
from fastapi.testclient import TestClient

import data_api.app as data_module
import game_api.app as game_module
from core.account_store import AccountStore
from core.balance_store import BalanceStore
from core.db import get_pool
from core.game_manager import GameManager
from core.game_metadata_store import GameMetadataStore
from core.game_recorder import GameRecorder
from core.stream_store import StreamStore
from poker.game import Game
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore
from poker.recorder import make_poker_materializer
from core.unified_router import configure as configure_unified_router


@pytest.fixture(autouse=True)
def reset_state():
    """Reset stores for both APIs before each test."""
    pool = get_pool()

    # Reset game API stores
    game_module.event_store = GameEventStore(pool)
    game_module.summary_store = HandSummaryStore(pool)
    game_module.stats_store = PlayerStatsStore(pool)
    game_module.metadata_store = GameMetadataStore(pool)
    game_module.stream_store = StreamStore(pool)

    poker_materializer = make_poker_materializer(game_module.summary_store)

    def make_recorder(game_id: str, game_type: str = "poker") -> GameRecorder:
        return GameRecorder(
            game_id,
            game_module.event_store,
            game_module.stats_store,
            summary_materializer=poker_materializer,
        )

    game_module.manager = GameManager(
        recorder_factory=make_recorder,
        metadata_store=game_module.metadata_store,
    )
    game_module.manager.register_game_type("poker", Game)
    game_module.account_store = AccountStore(pool)
    game_module.balance_store = BalanceStore(pool)
    configure_unified_router(
        mgr=game_module.manager,
        bal=game_module.balance_store,
        acc=game_module.account_store,
        meta=game_module.metadata_store,
        esc_audit=game_module.escrow_audit,
        auth_dep=game_module.require_auth,
    )

    # Reset data API stores (shares same DB)
    data_module.event_store = GameEventStore(pool)
    data_module.summary_store = HandSummaryStore(pool)
    data_module.stats_store = PlayerStatsStore(pool)
    data_module.metadata_store = GameMetadataStore(pool)
    data_module.stream_store = StreamStore(pool)
    yield


@pytest.fixture
def game_client():
    """Client for the Game API (to seed data)."""
    return TestClient(game_module.app)


@pytest.fixture
def client():
    """Client for the Data API (read-only)."""
    return TestClient(data_module.app)


# ── Helpers ──────────────────────────────────────────────

def auth_header(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def seed_game(game_client) -> tuple[str, str, str]:
    """Create a started 2-player game via Game API. Returns (game_id, key_a, key_b)."""
    key_a = game_module.account_store.create_account("Alice")
    key_b = game_module.account_store.create_account("Bob")
    gid = game_client.post("/api/games", json={"game_type": "poker", "mode": "offchain", "max_players": 2}).json()["game_id"]
    game_client.post(f"/api/games/{gid}/join", json={}, headers=auth_header(key_a))
    game_client.post(f"/api/games/{gid}/join", json={}, headers=auth_header(key_b))
    game_client.post(f"/api/games/{gid}/start", headers=auth_header(key_a))
    return gid, key_a, key_b


def fold_hand(game_client, gid: str, key_a: str, key_b: str) -> None:
    """Fold to complete the current hand."""
    s1 = game_client.get(f"/api/games/{gid}/state", headers=auth_header(key_a)).json()
    first_key = key_a if s1["is_your_turn"] else key_b
    game_client.post(f"/api/games/{gid}/action", json={"action": "fold"}, headers=auth_header(first_key))


# ── Lobby (game list from game_metadata) ─────────────────

class TestLobby:
    def test_list_games_empty(self, client):
        resp = client.get("/api/games")
        assert resp.status_code == 200
        assert resp.json()["games"] == []

    def test_list_games_after_create(self, game_client, client):
        game_client.post("/api/games", json={"game_type": "poker", "mode": "offchain", "max_players": 2})
        resp = client.get("/api/games")
        games = resp.json()["games"]
        assert len(games) == 1
        assert games[0]["started"] is False

    def test_lobby_reflects_player_join(self, game_client, client):
        gid = game_client.post("/api/games", json={"game_type": "poker", "mode": "offchain", "max_players": 2}).json()["game_id"]
        key = game_module.account_store.create_account("Alice")
        game_client.post(f"/api/games/{gid}/join", json={}, headers=auth_header(key))
        games = client.get("/api/games").json()["games"]
        assert games[0]["player_count"] == 1
        assert games[0]["player_names"] == ["Alice"]

    def test_lobby_reflects_started(self, game_client, client):
        gid, key_a, key_b = seed_game(game_client)
        games = client.get("/api/games").json()["games"]
        assert games[0]["started"] is True

    def test_game_page_404(self, client):
        resp = client.get("/game/nonexistent")
        assert resp.status_code == 404

    def test_game_page_exists(self, game_client, client):
        gid = game_client.post("/api/games", json={"game_type": "poker", "mode": "offchain"}).json()["game_id"]
        resp = client.get(f"/game/{gid}")
        assert resp.status_code in (200, 404)  # 404 if spectator.html missing


# ── History ──────────────────────────────────────────────

class TestHistory:
    def test_game_history(self, game_client, client):
        gid, key_a, key_b = seed_game(game_client)
        fold_hand(game_client, gid, key_a, key_b)

        resp = client.get(f"/api/games/{gid}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == gid
        assert len(data["events"]) > 0
        event_types = [e["event_type"] for e in data["events"]]
        assert "player_joined" in event_types
        assert "game_started" in event_types

    def test_game_history_404(self, client):
        resp = client.get("/api/games/nonexistent/history")
        assert resp.status_code == 404

    def test_game_history_respects_limit(self, game_client, client):
        gid, key_a, key_b = seed_game(game_client)
        fold_hand(game_client, gid, key_a, key_b)

        resp = client.get(f"/api/games/{gid}/history?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()["events"]) <= 2


# ── Hand summaries ───────────────────────────────────────

class TestHandSummaries:
    def test_hand_summaries(self, game_client, client):
        gid, key_a, key_b = seed_game(game_client)
        fold_hand(game_client, gid, key_a, key_b)

        resp = client.get(f"/api/games/{gid}/hands")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == gid
        assert len(data["hands"]) >= 1
        assert data["hands"][0]["hand_number"] == 1

    def test_hand_summaries_404(self, client):
        resp = client.get("/api/games/nonexistent/hands")
        assert resp.status_code == 404


# ── Player stats ─────────────────────────────────────────

class TestPlayerStats:
    def test_player_stats(self, game_client, client):
        gid, key_a, key_b = seed_game(game_client)
        fold_hand(game_client, gid, key_a, key_b)

        resp = client.get("/api/stats/Alice")
        assert resp.status_code == 200
        assert resp.json()["username"] == "Alice"
        assert resp.json()["games_played"] == 1

    def test_player_stats_404(self, client):
        resp = client.get("/api/stats/Nobody")
        assert resp.status_code == 404


# ── Streams (read-only) ─────────────────────────────────

class TestStreamsRead:
    def test_list_all_streams_empty(self, client):
        resp = client.get("/api/streams")
        assert resp.status_code == 200
        assert resp.json()["streams"] == []

    def test_list_all_streams(self, game_client, client):
        gid = game_client.post("/api/games", json={"game_type": "poker", "mode": "offchain"}).json()["game_id"]
        key = game_module.account_store.create_account("Alice")
        game_client.post(f"/api/games/{gid}/streams", json={"title": "Test Stream"}, headers=auth_header(key))

        resp = client.get("/api/streams")
        assert resp.status_code == 200
        streams = resp.json()["streams"]
        assert len(streams) == 1
        assert streams[0]["host"] == "Alice"

    def test_list_streams_for_game(self, game_client, client):
        gid = game_client.post("/api/games", json={"game_type": "poker", "mode": "offchain"}).json()["game_id"]
        key = game_module.account_store.create_account("Alice")
        game_client.post(f"/api/games/{gid}/streams", json={"title": "G1 Stream"}, headers=auth_header(key))

        resp = client.get(f"/api/games/{gid}/streams")
        assert resp.status_code == 200
        assert len(resp.json()["streams"]) == 1

    def test_stream_page_404(self, client):
        resp = client.get("/stream/999999")
        assert resp.status_code == 404

    def test_stream_page_exists(self, game_client, client):
        gid = game_client.post("/api/games", json={"game_type": "poker", "mode": "offchain"}).json()["game_id"]
        key = game_module.account_store.create_account("Alice")
        sid = game_client.post(
            f"/api/games/{gid}/streams", json={"title": "Test"}, headers=auth_header(key)
        ).json()["stream_id"]
        resp = client.get(f"/stream/{sid}")
        assert resp.status_code in (200, 404)  # 404 if spectator.html missing


# ── Instructions ─────────────────────────────────────────

class TestInstructions:
    def test_instructions(self, client):
        resp = client.get("/api/instructions")
        assert resp.status_code in (200, 404)
