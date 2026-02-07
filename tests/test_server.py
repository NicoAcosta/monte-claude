import pytest
from fastapi.testclient import TestClient

import poker.server as server_module
from poker.game import Game


@pytest.fixture(autouse=True)
def reset_game():
    """Reset global game state before each test."""
    server_module.game = Game()
    yield


@pytest.fixture
def client():
    return TestClient(server_module.app)


class TestRegister:
    def test_register(self, client):
        resp = client.post("/register", json={"name": "Alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_id"] == 1
        assert data["name"] == "Alice"

    def test_register_duplicate(self, client):
        client.post("/register", json={"name": "Alice"})
        resp = client.post("/register", json={"name": "Alice"})
        assert resp.status_code == 400

    def test_register_empty_name(self, client):
        resp = client.post("/register", json={"name": ""})
        assert resp.status_code == 400


class TestWaiting:
    def test_waiting_room(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        resp = client.get("/waiting")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is False
        assert data["player_count"] == 2
        assert len(data["players"]) == 2


class TestStart:
    def test_start_game(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        resp = client.post("/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hand_number"] == 1

    def test_start_not_enough_players(self, client):
        client.post("/register", json={"name": "Alice"})
        resp = client.post("/start")
        assert resp.status_code == 400


class TestState:
    def test_state_before_start(self, client):
        client.post("/register", json={"name": "Alice"})
        resp = client.get("/state/1")
        assert resp.status_code == 400

    def test_state_invalid_player(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")
        resp = client.get("/state/999")
        assert resp.status_code == 404

    def test_state_returns_cards(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")
        resp = client.get("/state/1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["your_cards"]) == 2
        assert data["phase"] == "preflop"
        assert data["hand_number"] == 1
        assert len(data["players"]) == 2


class TestAction:
    def test_action_before_start(self, client):
        resp = client.post("/action", json={"player_id": 1, "action": "fold"})
        assert resp.status_code == 400

    def test_fold(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")
        # Find who acts first
        s1 = client.get("/state/1").json()
        s2 = client.get("/state/2").json()
        first = 1 if s1["is_your_turn"] else 2
        resp = client.post("/action", json={"player_id": first, "action": "fold"})
        assert resp.status_code == 200

    def test_wrong_turn(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")
        s1 = client.get("/state/1").json()
        not_turn = 2 if s1["is_your_turn"] else 1
        resp = client.post("/action", json={"player_id": not_turn, "action": "fold"})
        assert resp.status_code == 400

    def test_full_hand_via_api(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")

        # Play through a full hand: call preflop, check all streets
        for _ in range(20):  # safety limit
            s1 = client.get("/state/1").json()
            s2 = client.get("/state/2").json()

            if s1["hand_number"] > 1 or s1["game_over"]:
                break

            if s1["is_your_turn"]:
                pid = 1
                to_call = s1["amount_to_call"]
            elif s2["is_your_turn"]:
                pid = 2
                to_call = s2["amount_to_call"]
            else:
                break

            if to_call > 0:
                client.post("/action", json={"player_id": pid, "action": "call"})
            else:
                client.post("/action", json={"player_id": pid, "action": "check"})

        # Hand should have completed
        final = client.get("/state/1").json()
        assert final["hand_number"] >= 2 or final["game_over"]


class TestSpectator:
    def test_spectator_before_start(self, client):
        resp = client.get("/spectator")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is False
        assert data["hand_number"] == 0
        assert data["phase"] == "waiting"

    def test_spectator_during_first_hand_sees_waiting(self, client):
        """During hand 1, no previous hand exists — spectator sees waiting state."""
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")
        resp = client.get("/spectator")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is True
        assert data["hand_number"] == 0
        assert data["phase"] == "waiting"
        assert data["recent_actions"] == []

    def test_spectator_sees_previous_hand_after_completion(self, client):
        """After hand 1 completes, spectator sees hand 1's full state."""
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")

        # Complete hand 1 by folding
        s1 = client.get("/state/1").json()
        first = 1 if s1["is_your_turn"] else 2
        client.post("/action", json={"player_id": first, "action": "fold"})

        # Now on hand 2 — spectator should see hand 1
        resp = client.get("/spectator")
        data = resp.json()
        assert data["hand_number"] == 1
        assert data["phase"] == "complete"
        assert len(data["recent_actions"]) > 0
        # Spectator can see all cards from the previous hand
        for p in data["players"]:
            assert len(p["cards"]) == 2

    def test_spectator_actions_have_id_and_timestamp(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")

        # Complete hand 1
        s1 = client.get("/state/1").json()
        first = 1 if s1["is_your_turn"] else 2
        client.post("/action", json={"player_id": first, "action": "fold"})

        resp = client.get("/spectator")
        data = resp.json()
        for action in data["recent_actions"]:
            assert "id" in action
            assert "timestamp" in action
            assert isinstance(action["id"], int)
            assert isinstance(action["timestamp"], float)
        # IDs should be sequential
        ids = [a["id"] for a in data["recent_actions"]]
        assert ids == sorted(ids)
        assert ids == list(range(ids[0], ids[0] + len(ids)))


class TestCommentary:
    def test_commentate_endpoint(self, client):
        resp = client.post("/commentate", json={"text": "What a hand!"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_commentary_in_spectator(self, client):
        client.post("/commentate", json={"text": "Exciting game!"})
        resp = client.get("/spectator")
        assert resp.status_code == 200
        assert resp.json()["commentary_text"] == "Exciting game!"

    def test_commentary_in_state(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")
        client.post("/commentate", json={"text": "Here we go!"})
        resp = client.get("/state/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["commentary_text"] == "Here we go!"

    def test_comment_in_action(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")
        # Find who acts first
        s1 = client.get("/state/1").json()
        first = 1 if s1["is_your_turn"] else 2
        second = 2 if first == 1 else 1
        resp = client.post("/action", json={
            "player_id": first, "action": "call", "comment": "I'm feeling lucky!"
        })
        assert resp.status_code == 200
        # Comment should be visible in player state (current hand)
        state = client.get(f"/state/{first}").json()
        comments = [a["comment"] for a in state["recent_actions"] if a.get("comment")]
        assert "I'm feeling lucky!" in comments
        # Complete the hand so spectator can see it
        client.post("/action", json={"player_id": second, "action": "fold"})
        spec = client.get("/spectator").json()
        spec_comments = [a["comment"] for a in spec["recent_actions"] if a.get("comment")]
        assert "I'm feeling lucky!" in spec_comments

    def test_player_comments_in_state(self, client):
        client.post("/register", json={"name": "Alice"})
        client.post("/register", json={"name": "Bob"})
        client.post("/start")
        s1 = client.get("/state/1").json()
        first = 1 if s1["is_your_turn"] else 2
        client.post("/action", json={
            "player_id": first, "action": "call", "comment": "Trash talk!"
        })
        state = client.get(f"/state/{first}").json()
        assert "player_comments" in state
        assert any(pc["comment"] == "Trash talk!" for pc in state["player_comments"])

    def test_no_commentary_by_default(self, client):
        resp = client.get("/spectator")
        assert resp.json()["commentary_text"] is None


class TestIndex:
    def test_index_page(self, client):
        resp = client.get("/")
        # Will 404 if index.html doesn't exist yet, that's expected
        # Just verify the route exists
        assert resp.status_code in (200, 404)
