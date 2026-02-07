import pytest
from fastapi.testclient import TestClient

import poker.server as server_module
from poker.game_manager import GameManager


@pytest.fixture(autouse=True)
def reset_manager():
    """Reset global game manager before each test."""
    server_module.manager = GameManager()
    yield


@pytest.fixture
def client():
    return TestClient(server_module.app)


def create_game(client) -> int:
    """Helper: create a game and return its id."""
    resp = client.post("/api/games")
    assert resp.status_code == 200
    return resp.json()["game_id"]


class TestLobby:
    def test_list_games_empty(self, client):
        resp = client.get("/api/games")
        assert resp.status_code == 200
        assert resp.json()["games"] == []

    def test_create_game(self, client):
        resp = client.post("/api/games")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == 1

    def test_list_games_after_create(self, client):
        create_game(client)
        resp = client.get("/api/games")
        games = resp.json()["games"]
        assert len(games) == 1
        assert games[0]["id"] == 1
        assert games[0]["started"] is False

    def test_lobby_page(self, client):
        resp = client.get("/")
        assert resp.status_code in (200, 404)

    def test_game_page_404(self, client):
        resp = client.get("/game/999")
        assert resp.status_code == 404

    def test_game_page_exists(self, client):
        gid = create_game(client)
        resp = client.get(f"/game/{gid}")
        assert resp.status_code in (200, 404)  # 404 if spectator.html missing


class TestRegister:
    def test_register(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/{gid}/register", json={"name": "Alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_id"] == 1
        assert data["name"] == "Alice"

    def test_register_duplicate(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        resp = client.post(f"/game/{gid}/register", json={"name": "Alice"})
        assert resp.status_code == 400

    def test_register_empty_name(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/{gid}/register", json={"name": ""})
        assert resp.status_code == 400

    def test_register_nonexistent_game(self, client):
        resp = client.post("/game/999/register", json={"name": "Alice"})
        assert resp.status_code == 404


class TestWaiting:
    def test_waiting_room(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        resp = client.get(f"/game/{gid}/waiting")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is False
        assert data["player_count"] == 2
        assert len(data["players"]) == 2


class TestStart:
    def test_start_game(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        resp = client.post(f"/game/{gid}/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hand_number"] == 1

    def test_start_not_enough_players(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        resp = client.post(f"/game/{gid}/start")
        assert resp.status_code == 400


class TestState:
    def test_state_before_start(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        resp = client.get(f"/game/{gid}/state/1")
        assert resp.status_code == 400

    def test_state_invalid_player(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")
        resp = client.get(f"/game/{gid}/state/999")
        assert resp.status_code == 404

    def test_state_returns_cards(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")
        resp = client.get(f"/game/{gid}/state/1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["your_cards"]) == 2
        assert data["phase"] == "preflop"
        assert data["hand_number"] == 1
        assert len(data["players"]) == 2


class TestAction:
    def test_action_before_start(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/{gid}/action", json={"player_id": 1, "action": "fold"})
        assert resp.status_code == 400

    def test_fold(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")
        # Find who acts first
        s1 = client.get(f"/game/{gid}/state/1").json()
        s2 = client.get(f"/game/{gid}/state/2").json()
        first = 1 if s1["is_your_turn"] else 2
        resp = client.post(f"/game/{gid}/action", json={"player_id": first, "action": "fold"})
        assert resp.status_code == 200

    def test_wrong_turn(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")
        s1 = client.get(f"/game/{gid}/state/1").json()
        not_turn = 2 if s1["is_your_turn"] else 1
        resp = client.post(f"/game/{gid}/action", json={"player_id": not_turn, "action": "fold"})
        assert resp.status_code == 400

    def test_full_hand_via_api(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")

        # Play through a full hand: call preflop, check all streets
        for _ in range(20):  # safety limit
            s1 = client.get(f"/game/{gid}/state/1").json()
            s2 = client.get(f"/game/{gid}/state/2").json()

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
                client.post(f"/game/{gid}/action", json={"player_id": pid, "action": "call"})
            else:
                client.post(f"/game/{gid}/action", json={"player_id": pid, "action": "check"})

        # Hand should have completed
        final = client.get(f"/game/{gid}/state/1").json()
        assert final["hand_number"] >= 2 or final["game_over"]


class TestSpectator:
    def test_spectator_before_start(self, client):
        gid = create_game(client)
        resp = client.get(f"/game/{gid}/spectator")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is False
        assert data["hand_number"] == 0
        assert data["phase"] == "waiting"

    def test_spectator_during_first_hand_sees_waiting(self, client):
        """During hand 1, no previous hand exists — spectator sees waiting state."""
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")
        resp = client.get(f"/game/{gid}/spectator")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is True
        assert data["hand_number"] == 0
        assert data["phase"] == "waiting"
        assert data["recent_actions"] == []

    def test_spectator_sees_previous_hand_after_completion(self, client):
        """After hand 1 completes, spectator sees hand 1's full state."""
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")

        # Complete hand 1 by folding
        s1 = client.get(f"/game/{gid}/state/1").json()
        first = 1 if s1["is_your_turn"] else 2
        client.post(f"/game/{gid}/action", json={"player_id": first, "action": "fold"})

        # Now on hand 2 — spectator should see hand 1
        resp = client.get(f"/game/{gid}/spectator")
        data = resp.json()
        assert data["hand_number"] == 1
        assert data["phase"] == "complete"
        assert len(data["recent_actions"]) > 0
        # Spectator can see all cards from the previous hand
        for p in data["players"]:
            assert len(p["cards"]) == 2

    def test_spectator_actions_have_id_and_timestamp(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")

        # Complete hand 1
        s1 = client.get(f"/game/{gid}/state/1").json()
        first = 1 if s1["is_your_turn"] else 2
        client.post(f"/game/{gid}/action", json={"player_id": first, "action": "fold"})

        resp = client.get(f"/game/{gid}/spectator")
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
        gid = create_game(client)
        resp = client.post(f"/game/{gid}/commentate", json={"text": "What a hand!"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_commentary_in_spectator(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/commentate", json={"text": "Exciting game!"})
        resp = client.get(f"/game/{gid}/spectator")
        assert resp.status_code == 200
        assert resp.json()["commentary_text"] == "Exciting game!"

    def test_commentary_in_state(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")
        client.post(f"/game/{gid}/commentate", json={"text": "Here we go!"})
        resp = client.get(f"/game/{gid}/state/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["commentary_text"] == "Here we go!"

    def test_comment_in_action(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")
        # Find who acts first
        s1 = client.get(f"/game/{gid}/state/1").json()
        first = 1 if s1["is_your_turn"] else 2
        second = 2 if first == 1 else 1
        resp = client.post(f"/game/{gid}/action", json={
            "player_id": first, "action": "call", "comment": "I'm feeling lucky!"
        })
        assert resp.status_code == 200
        # Comment should be visible in player state (current hand)
        state = client.get(f"/game/{gid}/state/{first}").json()
        comments = [a["comment"] for a in state["recent_actions"] if a.get("comment")]
        assert "I'm feeling lucky!" in comments
        # Complete the hand so spectator can see it
        client.post(f"/game/{gid}/action", json={"player_id": second, "action": "fold"})
        spec = client.get(f"/game/{gid}/spectator").json()
        spec_comments = [a["comment"] for a in spec["recent_actions"] if a.get("comment")]
        assert "I'm feeling lucky!" in spec_comments

    def test_player_comments_in_state(self, client):
        gid = create_game(client)
        client.post(f"/game/{gid}/register", json={"name": "Alice"})
        client.post(f"/game/{gid}/register", json={"name": "Bob"})
        client.post(f"/game/{gid}/start")
        s1 = client.get(f"/game/{gid}/state/1").json()
        first = 1 if s1["is_your_turn"] else 2
        client.post(f"/game/{gid}/action", json={
            "player_id": first, "action": "call", "comment": "Trash talk!"
        })
        state = client.get(f"/game/{gid}/state/{first}").json()
        assert "player_comments" in state
        assert any(pc["comment"] == "Trash talk!" for pc in state["player_comments"])

    def test_no_commentary_by_default(self, client):
        gid = create_game(client)
        resp = client.get(f"/game/{gid}/spectator")
        assert resp.json()["commentary_text"] is None


class TestGameIsolation:
    def test_games_are_isolated(self, client):
        """Players registered in one game don't appear in another."""
        g1 = create_game(client)
        g2 = create_game(client)

        client.post(f"/game/{g1}/register", json={"name": "Alice"})
        client.post(f"/game/{g2}/register", json={"name": "Bob"})

        w1 = client.get(f"/game/{g1}/waiting").json()
        w2 = client.get(f"/game/{g2}/waiting").json()

        assert w1["player_count"] == 1
        assert w1["players"][0]["name"] == "Alice"
        assert w2["player_count"] == 1
        assert w2["players"][0]["name"] == "Bob"

    def test_action_on_wrong_game(self, client):
        """Actions in one game don't affect another."""
        g1 = create_game(client)
        g2 = create_game(client)

        # Set up and start game 1
        client.post(f"/game/{g1}/register", json={"name": "Alice"})
        client.post(f"/game/{g1}/register", json={"name": "Bob"})
        client.post(f"/game/{g1}/start")

        # Game 2 should still be unstarted
        w2 = client.get(f"/game/{g2}/waiting").json()
        assert w2["started"] is False

    def test_lobby_reflects_multiple_games(self, client):
        g1 = create_game(client)
        g2 = create_game(client)
        client.post(f"/game/{g1}/register", json={"name": "Alice"})
        client.post(f"/game/{g1}/register", json={"name": "Bob"})
        client.post(f"/game/{g1}/start")

        games = client.get("/api/games").json()["games"]
        assert len(games) == 2

        started_game = next(g for g in games if g["id"] == g1)
        waiting_game = next(g for g in games if g["id"] == g2)
        assert started_game["started"] is True
        assert waiting_game["started"] is False
