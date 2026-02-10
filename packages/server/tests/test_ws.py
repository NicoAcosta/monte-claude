"""Tests for WebSocket endpoints."""

import json

import pytest
from starlette.testclient import TestClient

from game_api.app import app, account_store, manager, event_bus


def _create_started_poker(client: TestClient, prefix: str = "ws") -> tuple[str, str, str]:
    """Register 2 players, create and start a poker game.

    Returns (game_id, api_key1, api_key2).
    """
    key1 = account_store.create_account(f"{prefix}_alice")
    key2 = account_store.create_account(f"{prefix}_bob")

    resp = client.post(
        "/game/poker/games",
        json={"max_players": 2, "mode": "offchain"},
        headers={"X-API-Key": key1},
    )
    assert resp.status_code == 200, resp.text
    game_id = resp.json()["game_id"]

    client.post(f"/game/poker/{game_id}/join", json={}, headers={"X-API-Key": key1})
    client.post(f"/game/poker/{game_id}/join", json={}, headers={"X-API-Key": key2})
    client.post(f"/game/poker/{game_id}/start", json={}, headers={"X-API-Key": key1})

    return game_id, key1, key2


class TestSpectatorWebSocket:
    """Test spectator WebSocket endpoint."""

    def test_spectator_receives_initial_state(self):
        with TestClient(app) as client:
            game_id, _, _ = _create_started_poker(client, "spec_init")
            with client.websocket_connect(f"/ws/game/{game_id}/spectator") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "state", f"Expected state, got: {msg}"
                assert "data" in msg
                assert "state_version" in msg

    def test_spectator_game_not_found(self):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/game/nonexistent/spectator") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "not found" in msg["detail"].lower()

    def test_spectator_state_has_players(self):
        with TestClient(app) as client:
            game_id, _, _ = _create_started_poker(client, "spec_plrs")
            with client.websocket_connect(f"/ws/game/{game_id}/spectator") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "state"
                data = msg["data"]
                assert "players" in data
                assert len(data["players"]) == 2


class TestPlayerWebSocket:
    """Test player WebSocket endpoint."""

    def test_player_receives_initial_state(self):
        with TestClient(app) as client:
            game_id, key1, _ = _create_started_poker(client, "plr_init")
            with client.websocket_connect(f"/ws/game/{game_id}/player?api_key={key1}") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "state"
                assert "data" in msg
                # Player state includes personal cards
                assert "your_cards" in msg["data"]

    def test_player_no_api_key(self):
        with TestClient(app) as client:
            game_id, _, _ = _create_started_poker(client, "plr_nokey")
            with client.websocket_connect(f"/ws/game/{game_id}/player") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "missing" in msg["detail"].lower() or "api_key" in msg["detail"].lower()

    def test_player_invalid_api_key(self):
        with TestClient(app) as client:
            game_id, _, _ = _create_started_poker(client, "plr_badkey")
            with client.websocket_connect(f"/ws/game/{game_id}/player?api_key=pk_invalid") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "invalid" in msg["detail"].lower()

    def test_player_game_not_found(self):
        with TestClient(app) as client:
            key1 = account_store.create_account("plr_notfound_user")
            with client.websocket_connect(f"/ws/game/nonexistent/player?api_key={key1}") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "not found" in msg["detail"].lower()

    def test_player_not_in_game(self):
        with TestClient(app) as client:
            game_id, _, _ = _create_started_poker(client, "plr_notingame")
            # Create a third player who is NOT in the game
            outsider_key = account_store.create_account("plr_outsider")
            with client.websocket_connect(f"/ws/game/{game_id}/player?api_key={outsider_key}") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "not a player" in msg["detail"].lower()

    def test_player_receives_update_after_action(self):
        """When another player acts, the WS-connected player receives updated state."""
        with TestClient(app) as client:
            game_id, key1, key2 = _create_started_poker(client, "plr_update")
            with client.websocket_connect(f"/ws/game/{game_id}/player?api_key={key1}") as ws:
                # Receive initial state
                initial = ws.receive_json()
                assert initial["type"] == "state"

                state_data = initial["data"]
                if state_data["is_your_turn"]:
                    acting_key = key1
                else:
                    acting_key = key2

                # Perform action via HTTP
                client.post(
                    f"/game/poker/{game_id}/action",
                    json={"action": "fold"},
                    headers={"X-API-Key": acting_key},
                )

                # Should receive updated state via WS
                update = ws.receive_json()
                assert update["type"] == "state"
                assert "state_version" in update
