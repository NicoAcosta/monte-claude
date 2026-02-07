import pytest
from fastapi.testclient import TestClient

import poker.server as server_module
from poker.account_store import AccountStore
from poker.game_manager import GameManager
from poker.game_recorder import GameRecorder
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore


@pytest.fixture(autouse=True)
def reset_state(tmp_path):
    """Reset global game manager, account store, and history stores before each test."""
    server_module.event_store = GameEventStore(tmp_path / "events.csv")
    server_module.summary_store = HandSummaryStore(tmp_path / "summaries.csv")
    server_module.stats_store = PlayerStatsStore(tmp_path / "stats.csv")

    def make_recorder(game_id: int) -> GameRecorder:
        return GameRecorder(
            game_id,
            server_module.event_store,
            server_module.summary_store,
            server_module.stats_store,
        )

    server_module.manager = GameManager(recorder_factory=make_recorder)
    server_module.account_store = AccountStore(tmp_path / "accounts.csv")
    yield


@pytest.fixture
def client():
    return TestClient(server_module.app)


# ── Helpers ──────────────────────────────────────────────

def create_game(client) -> int:
    """Helper: create a game and return its id."""
    resp = client.post("/api/games")
    assert resp.status_code == 200
    return resp.json()["game_id"]


def register_account(client, username: str) -> str:
    """Helper: register an account and return the API key."""
    resp = client.post("/api/register", json={"username": username})
    assert resp.status_code == 200
    return resp.json()["api_key"]


def auth_header(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def join_game(client, game_id: int, api_key: str) -> dict:
    """Helper: join a game with an API key, return response json."""
    resp = client.post(f"/game/{game_id}/join", headers=auth_header(api_key))
    assert resp.status_code == 200
    return resp.json()


# ── Account Registration ────────────────────────────────

class TestAccountRegistration:
    def test_register_account(self, client):
        resp = client.post("/api/register", json={"username": "Alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "Alice"
        assert data["api_key"].startswith("pk_")

    def test_register_duplicate_username(self, client):
        register_account(client, "Alice")
        resp = client.post("/api/register", json={"username": "Alice"})
        assert resp.status_code == 400

    def test_register_empty_username(self, client):
        resp = client.post("/api/register", json={"username": ""})
        assert resp.status_code == 400


# ── Lobby ────────────────────────────────────────────────

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


# ── Join Game ────────────────────────────────────────────

class TestJoinGame:
    def test_join_game(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        data = join_game(client, gid, key)
        assert data["player_id"] == 1
        assert data["name"] == "Alice"

    def test_join_requires_auth(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/{gid}/join")
        assert resp.status_code == 401

    def test_join_invalid_key(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/{gid}/join", headers=auth_header("pk_bogus"))
        assert resp.status_code == 401

    def test_join_duplicate_name(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        join_game(client, gid, key)
        # Same user can't join twice (game.register rejects duplicate name)
        resp = client.post(f"/game/{gid}/join", headers=auth_header(key))
        assert resp.status_code == 400

    def test_join_nonexistent_game(self, client):
        key = register_account(client, "Alice")
        resp = client.post("/game/999/join", headers=auth_header(key))
        assert resp.status_code == 404


# ── Waiting ──────────────────────────────────────────────

class TestWaiting:
    def test_waiting_room(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        resp = client.get(f"/game/{gid}/waiting")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is False
        assert data["player_count"] == 2
        assert len(data["players"]) == 2


# ── Start ────────────────────────────────────────────────

class TestStart:
    def test_start_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        resp = client.post(f"/game/{gid}/start", headers=auth_header(key_a))
        assert resp.status_code == 200
        data = resp.json()
        assert data["hand_number"] == 1

    def test_start_not_enough_players(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        join_game(client, gid, key)
        resp = client.post(f"/game/{gid}/start", headers=auth_header(key))
        assert resp.status_code == 400

    def test_start_requires_auth(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/{gid}/start")
        assert resp.status_code == 401

    def test_start_non_player_forbidden(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        key_c = register_account(client, "Charlie")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        # Charlie has a valid key but isn't in the game
        resp = client.post(f"/game/{gid}/start", headers=auth_header(key_c))
        assert resp.status_code == 403


# ── State ────────────────────────────────────────────────

class TestState:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def test_state_before_start(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        join_game(client, gid, key)
        resp = client.get(f"/game/{gid}/state/1")
        assert resp.status_code == 400

    def test_state_invalid_player(self, client):
        gid, _, _ = self._setup_started_game(client)
        resp = client.get(f"/game/{gid}/state/999")
        assert resp.status_code == 404

    def test_state_returns_cards(self, client):
        gid, _, _ = self._setup_started_game(client)
        resp = client.get(f"/game/{gid}/state/1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["your_cards"]) == 2
        assert data["phase"] == "preflop"
        assert data["hand_number"] == 1
        assert len(data["players"]) == 2

    def test_state_no_auth_required(self, client):
        """State endpoint is read-only, no auth needed."""
        gid, _, _ = self._setup_started_game(client)
        resp = client.get(f"/game/{gid}/state/1")
        assert resp.status_code == 200


# ── Action ───────────────────────────────────────────────

class TestAction:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def _who_acts_first(self, client, gid, key_a, key_b):
        s1 = client.get(f"/game/{gid}/state/1").json()
        s2 = client.get(f"/game/{gid}/state/2").json()
        if s1["is_your_turn"]:
            return key_a, key_b
        return key_b, key_a

    def test_action_requires_auth(self, client):
        gid, _, _ = self._setup_started_game(client)
        resp = client.post(f"/game/{gid}/action", json={"action": "fold"})
        assert resp.status_code == 401

    def test_action_invalid_key(self, client):
        gid, _, _ = self._setup_started_game(client)
        resp = client.post(
            f"/game/{gid}/action",
            json={"action": "fold"},
            headers=auth_header("pk_bogus"),
        )
        assert resp.status_code == 401

    def test_action_non_player_404(self, client):
        gid, _, _ = self._setup_started_game(client)
        key_c = register_account(client, "Charlie")
        resp = client.post(
            f"/game/{gid}/action",
            json={"action": "fold"},
            headers=auth_header(key_c),
        )
        assert resp.status_code == 404

    def test_fold(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        first_key, _ = self._who_acts_first(client, gid, key_a, key_b)
        resp = client.post(
            f"/game/{gid}/action",
            json={"action": "fold"},
            headers=auth_header(first_key),
        )
        assert resp.status_code == 200

    def test_wrong_turn(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        _, second_key = self._who_acts_first(client, gid, key_a, key_b)
        resp = client.post(
            f"/game/{gid}/action",
            json={"action": "fold"},
            headers=auth_header(second_key),
        )
        assert resp.status_code == 400

    def test_full_hand_via_api(self, client):
        gid, key_a, key_b = self._setup_started_game(client)

        # Play through a full hand: call preflop, check all streets
        for _ in range(20):  # safety limit
            s1 = client.get(f"/game/{gid}/state/1").json()
            s2 = client.get(f"/game/{gid}/state/2").json()

            if s1["hand_number"] > 1 or s1["game_over"]:
                break

            if s1["is_your_turn"]:
                key = key_a
                to_call = s1["amount_to_call"]
            elif s2["is_your_turn"]:
                key = key_b
                to_call = s2["amount_to_call"]
            else:
                break

            if to_call > 0:
                client.post(f"/game/{gid}/action", json={"action": "call"}, headers=auth_header(key))
            else:
                client.post(f"/game/{gid}/action", json={"action": "check"}, headers=auth_header(key))

        # Hand should have completed
        final = client.get(f"/game/{gid}/state/1").json()
        assert final["hand_number"] >= 2 or final["game_over"]


# ── Spectator ────────────────────────────────────────────

class TestSpectator:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

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
        gid, _, _ = self._setup_started_game(client)
        resp = client.get(f"/game/{gid}/spectator")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is True
        assert data["hand_number"] == 0
        assert data["phase"] == "waiting"
        assert data["recent_actions"] == []

    def test_spectator_sees_previous_hand_after_completion(self, client):
        """After hand 1 completes, spectator sees hand 1's full state."""
        gid, key_a, key_b = self._setup_started_game(client)

        # Complete hand 1 by folding
        s1 = client.get(f"/game/{gid}/state/1").json()
        first_key = key_a if s1["is_your_turn"] else key_b
        client.post(f"/game/{gid}/action", json={"action": "fold"}, headers=auth_header(first_key))

        # Now on hand 2 — spectator should see hand 1
        resp = client.get(f"/game/{gid}/spectator")
        data = resp.json()
        assert data["hand_number"] == 1
        assert data["phase"] == "complete"
        assert len(data["recent_actions"]) > 0
        for p in data["players"]:
            assert len(p["cards"]) == 2

    def test_spectator_actions_have_id_and_timestamp(self, client):
        gid, key_a, key_b = self._setup_started_game(client)

        s1 = client.get(f"/game/{gid}/state/1").json()
        first_key = key_a if s1["is_your_turn"] else key_b
        client.post(f"/game/{gid}/action", json={"action": "fold"}, headers=auth_header(first_key))

        resp = client.get(f"/game/{gid}/spectator")
        data = resp.json()
        for a in data["recent_actions"]:
            assert "id" in a
            assert "timestamp" in a
            assert isinstance(a["id"], int)
            assert isinstance(a["timestamp"], float)
        ids = [a["id"] for a in data["recent_actions"]]
        assert ids == sorted(ids)
        assert ids == list(range(ids[0], ids[0] + len(ids)))

    def test_spectator_no_auth_required(self, client):
        """Spectator endpoint is read-only, no auth needed."""
        gid, _, _ = self._setup_started_game(client)
        resp = client.get(f"/game/{gid}/spectator")
        assert resp.status_code == 200


# ── Commentary ───────────────────────────────────────────

class TestCommentary:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def test_commentate_requires_auth(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/{gid}/commentate", json={"text": "Hello"})
        assert resp.status_code == 401

    def test_commentate_endpoint(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        resp = client.post(
            f"/game/{gid}/commentate",
            json={"text": "What a hand!"},
            headers=auth_header(key),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_commentary_in_spectator(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        client.post(
            f"/game/{gid}/commentate",
            json={"text": "Exciting game!"},
            headers=auth_header(key),
        )
        resp = client.get(f"/game/{gid}/spectator")
        assert resp.status_code == 200
        assert resp.json()["commentary_text"] == "Exciting game!"

    def test_commentary_in_state(self, client):
        gid, key_a, _ = self._setup_started_game(client)
        client.post(
            f"/game/{gid}/commentate",
            json={"text": "Here we go!"},
            headers=auth_header(key_a),
        )
        resp = client.get(f"/game/{gid}/state/1")
        assert resp.status_code == 200
        assert resp.json()["commentary_text"] == "Here we go!"

    def test_comment_in_action(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        s1 = client.get(f"/game/{gid}/state/1").json()
        first_key = key_a if s1["is_your_turn"] else key_b
        second_key = key_b if first_key == key_a else key_a
        first_pid = 1 if s1["is_your_turn"] else 2

        resp = client.post(
            f"/game/{gid}/action",
            json={"action": "call", "comment": "I'm feeling lucky!"},
            headers=auth_header(first_key),
        )
        assert resp.status_code == 200
        # Comment should be visible in player state
        state = client.get(f"/game/{gid}/state/{first_pid}").json()
        comments = [a["comment"] for a in state["recent_actions"] if a.get("comment")]
        assert "I'm feeling lucky!" in comments
        # Complete hand
        client.post(f"/game/{gid}/action", json={"action": "fold"}, headers=auth_header(second_key))
        spec = client.get(f"/game/{gid}/spectator").json()
        spec_comments = [a["comment"] for a in spec["recent_actions"] if a.get("comment")]
        assert "I'm feeling lucky!" in spec_comments

    def test_player_comments_in_state(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        s1 = client.get(f"/game/{gid}/state/1").json()
        first_key = key_a if s1["is_your_turn"] else key_b
        first_pid = 1 if s1["is_your_turn"] else 2

        client.post(
            f"/game/{gid}/action",
            json={"action": "call", "comment": "Trash talk!"},
            headers=auth_header(first_key),
        )
        state = client.get(f"/game/{gid}/state/{first_pid}").json()
        assert "player_comments" in state
        assert any(pc["comment"] == "Trash talk!" for pc in state["player_comments"])

    def test_no_commentary_by_default(self, client):
        gid = create_game(client)
        resp = client.get(f"/game/{gid}/spectator")
        assert resp.json()["commentary_text"] is None


# ── Game Isolation ───────────────────────────────────────

class TestGameIsolation:
    def test_games_are_isolated(self, client):
        """Players registered in one game don't appear in another."""
        g1 = create_game(client)
        g2 = create_game(client)

        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, g1, key_a)
        join_game(client, g2, key_b)

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

        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, g1, key_a)
        join_game(client, g1, key_b)
        client.post(f"/game/{g1}/start", headers=auth_header(key_a))

        w2 = client.get(f"/game/{g2}/waiting").json()
        assert w2["started"] is False

    def test_lobby_reflects_multiple_games(self, client):
        g1 = create_game(client)
        g2 = create_game(client)

        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, g1, key_a)
        join_game(client, g1, key_b)
        client.post(f"/game/{g1}/start", headers=auth_header(key_a))

        games = client.get("/api/games").json()["games"]
        assert len(games) == 2

        started_game = next(g for g in games if g["id"] == g1)
        waiting_game = next(g for g in games if g["id"] == g2)
        assert started_game["started"] is True
        assert waiting_game["started"] is False


# ── History Endpoints ───────────────────────────────────

class TestHistory:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def test_game_history_endpoint(self, client):
        gid, key_a, key_b = self._setup_started_game(client)

        # Fold to complete a hand
        s1 = client.get(f"/game/{gid}/state/1").json()
        first_key = key_a if s1["is_your_turn"] else key_b
        client.post(f"/game/{gid}/action", json={"action": "fold"}, headers=auth_header(first_key))

        resp = client.get(f"/api/games/{gid}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == gid
        assert len(data["events"]) > 0

        event_types = [e["event_type"] for e in data["events"]]
        assert "player_joined" in event_types
        assert "game_started" in event_types
        assert "hand_started" in event_types
        assert "action" in event_types
        assert "hand_completed" in event_types

    def test_game_history_404(self, client):
        resp = client.get("/api/games/999/history")
        assert resp.status_code == 404

    def test_hand_summaries_endpoint(self, client):
        gid, key_a, key_b = self._setup_started_game(client)

        s1 = client.get(f"/game/{gid}/state/1").json()
        first_key = key_a if s1["is_your_turn"] else key_b
        client.post(f"/game/{gid}/action", json={"action": "fold"}, headers=auth_header(first_key))

        resp = client.get(f"/api/games/{gid}/hands")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == gid
        assert len(data["hands"]) >= 1
        hand = data["hands"][0]
        assert hand["hand_number"] == 1
        assert hand["pot"] > 0
        assert len(hand["winner_ids"]) >= 1

    def test_player_stats_endpoint(self, client):
        gid, key_a, key_b = self._setup_started_game(client)

        s1 = client.get(f"/game/{gid}/state/1").json()
        first_key = key_a if s1["is_your_turn"] else key_b
        client.post(f"/game/{gid}/action", json={"action": "fold"}, headers=auth_header(first_key))

        resp_alice = client.get("/api/stats/Alice")
        assert resp_alice.status_code == 200
        alice = resp_alice.json()
        assert alice["username"] == "Alice"
        assert alice["games_played"] == 1
        assert alice["hands_played"] >= 1

        resp_bob = client.get("/api/stats/Bob")
        assert resp_bob.status_code == 200
        bob = resp_bob.json()
        assert bob["username"] == "Bob"
        assert bob["games_played"] == 1

    def test_player_stats_404(self, client):
        resp = client.get("/api/stats/Nobody")
        assert resp.status_code == 404
