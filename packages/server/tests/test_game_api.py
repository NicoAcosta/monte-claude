from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

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
from poker.router import configure as configure_poker_router


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global game manager, account store, balance store, and history stores before each test."""
    pool = get_pool()
    game_module.event_store = GameEventStore(pool)
    game_module.summary_store = HandSummaryStore(pool)
    game_module.stats_store = PlayerStatsStore(pool)
    game_module.metadata_store = GameMetadataStore(pool)
    game_module.stream_store = StreamStore(pool)

    poker_materializer = make_poker_materializer(game_module.summary_store)

    def make_recorder(game_id: int, game_type: str = "poker") -> GameRecorder:
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
    configure_poker_router(
        mgr=game_module.manager,
        bal=game_module.balance_store,
        acc=game_module.account_store,
        meta=game_module.metadata_store,
        esc_audit=game_module.escrow_audit,
        auth_dep=game_module.require_auth,
    )
    yield


@pytest.fixture
def client():
    return TestClient(game_module.app)


# ── Helpers ──────────────────────────────────────────────

def create_game(client, **kwargs) -> int:
    """Helper: create a game and return its id."""
    body = {"max_players": 0, "buy_in": 0, **kwargs}
    resp = client.post("/game/poker/games", json=body)
    assert resp.status_code == 200
    return resp.json()["game_id"]


def register_account(client, username: str) -> str:
    """Helper: register an account via store and return the API key."""
    return game_module.account_store.create_account(username)


def auth_header(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def join_game(client, game_id: int, api_key: str, wallet_address: str | None = None) -> dict:
    """Helper: join a game with an API key, return response json."""
    body = {"wallet_address": wallet_address}
    resp = client.post(f"/game/poker/{game_id}/join", json=body, headers=auth_header(api_key))
    assert resp.status_code == 200
    return resp.json()


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
        resp = client.post(f"/game/poker/{gid}/join", json={"wallet_address": None})
        assert resp.status_code == 401

    def test_join_invalid_key(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/poker/{gid}/join", json={"wallet_address": None}, headers=auth_header("pk_bogus"))
        assert resp.status_code == 401

    def test_join_duplicate_name(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        join_game(client, gid, key)
        # Same user can't join twice (game.register rejects duplicate name)
        resp = client.post(f"/game/poker/{gid}/join", json={"wallet_address": None}, headers=auth_header(key))
        assert resp.status_code == 400

    def test_join_nonexistent_game(self, client):
        key = register_account(client, "Alice")
        resp = client.post("/game/poker/999/join", json={"wallet_address": None}, headers=auth_header(key))
        assert resp.status_code == 404


# ── Waiting ──────────────────────────────────────────────

class TestWaiting:
    def test_waiting_room(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        resp = client.get(f"/game/poker/{gid}/waiting")
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
        resp = client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        assert resp.status_code == 200
        data = resp.json()
        assert data["hand_number"] == 1

    def test_start_not_enough_players(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        join_game(client, gid, key)
        resp = client.post(f"/game/poker/{gid}/start", headers=auth_header(key))
        assert resp.status_code == 400

    def test_start_requires_auth(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/poker/{gid}/start")
        assert resp.status_code == 401

    def test_start_non_player_forbidden(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        key_c = register_account(client, "Charlie")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        # Charlie has a valid key but isn't in the game
        resp = client.post(f"/game/poker/{gid}/start", headers=auth_header(key_c))
        assert resp.status_code == 403


# ── State ────────────────────────────────────────────────

class TestState:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def test_state_requires_auth(self, client):
        gid, _, _ = self._setup_started_game(client)
        resp = client.get(f"/game/poker/{gid}/state")
        assert resp.status_code == 401

    def test_state_non_player_rejected(self, client):
        gid, _, _ = self._setup_started_game(client)
        key_c = register_account(client, "Charlie")
        resp = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_c))
        assert resp.status_code == 403

    def test_state_before_start(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        join_game(client, gid, key)
        resp = client.get(f"/game/poker/{gid}/state", headers=auth_header(key))
        assert resp.status_code == 400

    def test_state_returns_cards(self, client):
        gid, key_a, _ = self._setup_started_game(client)
        resp = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["your_cards"]) == 2
        assert data["phase"] == "preflop"
        assert data["hand_number"] == 1
        assert len(data["players"]) == 2


# ── Action ───────────────────────────────────────────────

class TestAction:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def _who_acts_first(self, client, gid, key_a, key_b):
        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        if s1["is_your_turn"]:
            return key_a, key_b
        return key_b, key_a

    def test_action_requires_auth(self, client):
        gid, _, _ = self._setup_started_game(client)
        resp = client.post(f"/game/poker/{gid}/action", json={"action": "fold"})
        assert resp.status_code == 401

    def test_action_invalid_key(self, client):
        gid, _, _ = self._setup_started_game(client)
        resp = client.post(
            f"/game/poker/{gid}/action",
            json={"action": "fold"},
            headers=auth_header("pk_bogus"),
        )
        assert resp.status_code == 401

    def test_action_non_player_404(self, client):
        gid, _, _ = self._setup_started_game(client)
        key_c = register_account(client, "Charlie")
        resp = client.post(
            f"/game/poker/{gid}/action",
            json={"action": "fold"},
            headers=auth_header(key_c),
        )
        assert resp.status_code == 404

    def test_fold(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        first_key, _ = self._who_acts_first(client, gid, key_a, key_b)
        resp = client.post(
            f"/game/poker/{gid}/action",
            json={"action": "fold"},
            headers=auth_header(first_key),
        )
        assert resp.status_code == 200

    def test_wrong_turn(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        _, second_key = self._who_acts_first(client, gid, key_a, key_b)
        resp = client.post(
            f"/game/poker/{gid}/action",
            json={"action": "fold"},
            headers=auth_header(second_key),
        )
        assert resp.status_code == 400

    def test_full_hand_via_api(self, client):
        gid, key_a, key_b = self._setup_started_game(client)

        # Play through a full hand: call preflop, check all streets
        for _ in range(20):  # safety limit
            s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()

            if s1["hand_number"] > 1 or s1["game_over"]:
                break

            if s1["is_your_turn"]:
                key = key_a
                to_call = s1["amount_to_call"]
            else:
                s2 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_b)).json()
                if s2["is_your_turn"]:
                    key = key_b
                    to_call = s2["amount_to_call"]
                else:
                    break

            if to_call > 0:
                client.post(f"/game/poker/{gid}/action", json={"action": "call"}, headers=auth_header(key))
            else:
                client.post(f"/game/poker/{gid}/action", json={"action": "check"}, headers=auth_header(key))

        # Hand should have completed
        final = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        assert final["hand_number"] >= 2 or final["game_over"]


# ── Spectator ────────────────────────────────────────────

class TestSpectator:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def test_spectator_before_start(self, client):
        gid = create_game(client)
        resp = client.get(f"/game/poker/{gid}/spectator")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is False
        assert data["hand_number"] == 0
        assert data["phase"] == "waiting"

    def test_spectator_during_first_hand_sees_waiting(self, client):
        """During hand 1, no previous hand exists — spectator sees waiting state."""
        gid, _, _ = self._setup_started_game(client)
        resp = client.get(f"/game/poker/{gid}/spectator")
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
        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        first_key = key_a if s1["is_your_turn"] else key_b
        client.post(f"/game/poker/{gid}/action", json={"action": "fold"}, headers=auth_header(first_key))

        # Now on hand 2 — spectator should see hand 1
        resp = client.get(f"/game/poker/{gid}/spectator")
        data = resp.json()
        assert data["hand_number"] == 1
        assert data["phase"] == "complete"
        assert len(data["recent_actions"]) > 0
        for p in data["players"]:
            assert len(p["cards"]) == 2

    def test_spectator_actions_have_id_and_timestamp(self, client):
        gid, key_a, key_b = self._setup_started_game(client)

        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        first_key = key_a if s1["is_your_turn"] else key_b
        client.post(f"/game/poker/{gid}/action", json={"action": "fold"}, headers=auth_header(first_key))

        resp = client.get(f"/game/poker/{gid}/spectator")
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
        resp = client.get(f"/game/poker/{gid}/spectator")
        assert resp.status_code == 200


# ── Action Comments ───────────────────────────────────────

class TestActionComments:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def test_comment_too_long(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        first_key = key_a if s1["is_your_turn"] else key_b
        resp = client.post(
            f"/game/poker/{gid}/action",
            json={"action": "call", "comment": "x" * 141},
            headers=auth_header(first_key),
        )
        assert resp.status_code == 400
        assert "140" in resp.json()["detail"]

    def test_comment_at_max_length(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        first_key = key_a if s1["is_your_turn"] else key_b
        resp = client.post(
            f"/game/poker/{gid}/action",
            json={"action": "call", "comment": "x" * 140},
            headers=auth_header(first_key),
        )
        assert resp.status_code == 200

    def test_comment_in_action(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        first_key = key_a if s1["is_your_turn"] else key_b
        second_key = key_b if first_key == key_a else key_a

        resp = client.post(
            f"/game/poker/{gid}/action",
            json={"action": "call", "comment": "I'm feeling lucky!"},
            headers=auth_header(first_key),
        )
        assert resp.status_code == 200
        # Comment should be visible in player state
        state = client.get(f"/game/poker/{gid}/state", headers=auth_header(first_key)).json()
        comments = [a["comment"] for a in state["recent_actions"] if a.get("comment")]
        assert "I'm feeling lucky!" in comments
        # Complete hand
        client.post(f"/game/poker/{gid}/action", json={"action": "fold"}, headers=auth_header(second_key))
        spec = client.get(f"/game/poker/{gid}/spectator").json()
        spec_comments = [a["comment"] for a in spec["recent_actions"] if a.get("comment")]
        assert "I'm feeling lucky!" in spec_comments

    def test_player_comments_in_state(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        first_key = key_a if s1["is_your_turn"] else key_b

        client.post(
            f"/game/poker/{gid}/action",
            json={"action": "call", "comment": "Trash talk!"},
            headers=auth_header(first_key),
        )
        state = client.get(f"/game/poker/{gid}/state", headers=auth_header(first_key)).json()
        assert "player_comments" in state
        assert any(pc["comment"] == "Trash talk!" for pc in state["player_comments"])

    def test_no_commentary_in_spectator_by_default(self, client):
        gid = create_game(client)
        resp = client.get(f"/game/poker/{gid}/spectator")
        assert resp.json()["commentary_text"] is None

    def test_no_commentary_in_player_state(self, client):
        """commentary_text was removed from PlayerStateResponse."""
        gid, key_a, _ = self._setup_started_game(client)
        resp = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a))
        assert "commentary_text" not in resp.json()


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

        w1 = client.get(f"/game/poker/{g1}/waiting").json()
        w2 = client.get(f"/game/poker/{g2}/waiting").json()

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
        client.post(f"/game/poker/{g1}/start", headers=auth_header(key_a))

        w2 = client.get(f"/game/poker/{g2}/waiting").json()
        assert w2["started"] is False


# ── Chat ────────────────────────────────────────────────

class TestChat:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def test_chat_requires_auth(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/poker/{gid}/chat", json={"message": "Hello"})
        assert resp.status_code == 401

    def test_chat_requires_player(self, client):
        gid, _, _ = self._setup_started_game(client)
        key_c = register_account(client, "Charlie")
        resp = client.post(
            f"/game/poker/{gid}/chat",
            json={"message": "Hello"},
            headers=auth_header(key_c),
        )
        assert resp.status_code == 403

    def test_chat_empty_message(self, client):
        gid, key_a, _ = self._setup_started_game(client)
        resp = client.post(
            f"/game/poker/{gid}/chat",
            json={"message": "   "},
            headers=auth_header(key_a),
        )
        assert resp.status_code == 400

    def test_chat_too_long(self, client):
        gid, key_a, _ = self._setup_started_game(client)
        resp = client.post(
            f"/game/poker/{gid}/chat",
            json={"message": "x" * 141},
            headers=auth_header(key_a),
        )
        assert resp.status_code == 400

    def test_chat_at_max_length(self, client):
        gid, key_a, _ = self._setup_started_game(client)
        resp = client.post(
            f"/game/poker/{gid}/chat",
            json={"message": "x" * 140},
            headers=auth_header(key_a),
        )
        assert resp.status_code == 200

    def test_chat_success(self, client):
        gid, key_a, _ = self._setup_started_game(client)
        resp = client.post(
            f"/game/poker/{gid}/chat",
            json={"message": "Hello everyone!"},
            headers=auth_header(key_a),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_chat_in_state_response(self, client):
        gid, key_a, _ = self._setup_started_game(client)
        client.post(
            f"/game/poker/{gid}/chat",
            json={"message": "Good luck!"},
            headers=auth_header(key_a),
        )
        state = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        assert "chat_log" in state
        assert len(state["chat_log"]) == 1
        assert state["chat_log"][0]["player"] == "Alice"
        assert state["chat_log"][0]["message"] == "Good luck!"

    def test_chat_in_spectator_response(self, client):
        gid, key_a, _ = self._setup_started_game(client)
        client.post(
            f"/game/poker/{gid}/chat",
            json={"message": "GL HF"},
            headers=auth_header(key_a),
        )
        spec = client.get(f"/game/poker/{gid}/spectator").json()
        assert "chat_log" in spec
        assert len(spec["chat_log"]) == 1
        assert spec["chat_log"][0]["message"] == "GL HF"


# ── Timer ───────────────────────────────────────────────

class TestTimer:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def test_timer_in_state_response(self, client):
        gid, key_a, _ = self._setup_started_game(client)
        state = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        assert "timer" in state
        timer = state["timer"]
        assert timer is not None
        assert timer["action_timeout"] == 30.0
        assert timer["deadline"] is not None
        assert timer["extensions_remaining"] == 3

    def test_custom_extensions_per_player(self, client):
        gid = create_game(client, extensions_per_player=7)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        state = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        assert state["timer"]["extensions_remaining"] == 7

    def test_zero_extensions_per_player(self, client):
        gid = create_game(client, extensions_per_player=0)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        state = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        assert state["timer"]["extensions_remaining"] == 0

    def test_timer_in_spectator_response(self, client):
        gid, _, _ = self._setup_started_game(client)
        spec = client.get(f"/game/poker/{gid}/spectator").json()
        assert "timer" in spec
        # During hand 1 with no previous hand, spectator sees timer for live game
        timer = spec["timer"]
        assert timer is not None

    def test_extend_requires_auth(self, client):
        gid, _, _ = self._setup_started_game(client)
        resp = client.post(f"/game/poker/{gid}/extend")
        assert resp.status_code == 401

    def test_extend_requires_player(self, client):
        gid, _, _ = self._setup_started_game(client)
        key_c = register_account(client, "Charlie")
        resp = client.post(f"/game/poker/{gid}/extend", headers=auth_header(key_c))
        assert resp.status_code == 403

    def test_extend_wrong_turn(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        # Find who does NOT have the turn
        if s1["is_your_turn"]:
            wrong_key = key_b
        else:
            wrong_key = key_a
        resp = client.post(f"/game/poker/{gid}/extend", headers=auth_header(wrong_key))
        assert resp.status_code == 400

    def test_extend_success(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        right_key = key_a if s1["is_your_turn"] else key_b

        resp = client.post(f"/game/poker/{gid}/extend", headers=auth_header(right_key))
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["extensions_remaining"] == 2
        assert data["new_deadline"] > 0

    def test_extend_past_deadline_succeeds(self, client):
        """SE-1: extend must apply before timeout check, so a player 1ms past deadline
        can still extend instead of being auto-folded."""
        gid, key_a, key_b = self._setup_started_game(client)
        game = game_module.manager.get_game(gid)

        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        right_key = key_a if s1["is_your_turn"] else key_b

        # Move time to 1ms past the deadline
        deadline = game.turn_deadline
        with patch("poker.game.time.time", return_value=deadline + 0.001):
            resp = client.post(f"/game/poker/{gid}/extend", headers=auth_header(right_key))

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["extensions_remaining"] == 2

    def test_extend_past_deadline_no_extensions_left_folds(self, client):
        """SE-1: when extensions are exhausted and past deadline, the timeout check fires."""
        gid, key_a, key_b = self._setup_started_game(client)
        game = game_module.manager.get_game(gid)

        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        right_key = key_a if s1["is_your_turn"] else key_b
        player = game.get_player_by_name(
            "Alice" if right_key == key_a else "Bob"
        )

        # Exhaust all extensions
        for _ in range(game.extensions_per_player):
            game.use_extension(player.id)

        hand_before = game.hand_number
        deadline = game.turn_deadline

        # Now try to extend past deadline with no extensions left
        with patch("poker.game.time.time", return_value=deadline + 0.001):
            resp = client.post(f"/game/poker/{gid}/extend", headers=auth_header(right_key))

        # Should fail with 400 (no extensions left), and timeout check should have fired
        assert resp.status_code == 400
        # The timeout fold should have advanced the hand
        assert game.hand_number > hand_before


# ── Reason ─────────────────────────────────────────────

class TestReason:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def _who_acts_first(self, client, gid, key_a, key_b):
        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        if s1["is_your_turn"]:
            return key_a, key_b
        return key_b, key_a

    def test_reason_too_long(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        first_key, _ = self._who_acts_first(client, gid, key_a, key_b)
        resp = client.post(
            f"/game/poker/{gid}/action",
            json={"action": "call", "reason": "x" * 501},
            headers=auth_header(first_key),
        )
        assert resp.status_code == 400
        assert "500" in resp.json()["detail"]

    def test_reason_at_max_length(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        first_key, _ = self._who_acts_first(client, gid, key_a, key_b)
        resp = client.post(
            f"/game/poker/{gid}/action",
            json={"action": "call", "reason": "x" * 500},
            headers=auth_header(first_key),
        )
        assert resp.status_code == 200

    def test_reason_hidden_from_player_state(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        first_key, second_key = self._who_acts_first(client, gid, key_a, key_b)

        client.post(
            f"/game/poker/{gid}/action",
            json={"action": "call", "reason": "I have pocket aces"},
            headers=auth_header(first_key),
        )
        # Both players should NOT see reason in state
        for key in (first_key, second_key):
            state = client.get(f"/game/poker/{gid}/state", headers=auth_header(key)).json()
            for a in state["recent_actions"]:
                assert a.get("reason") is None

    def test_reason_visible_in_spectator(self, client):
        gid, key_a, key_b = self._setup_started_game(client)
        first_key, second_key = self._who_acts_first(client, gid, key_a, key_b)

        # Act with reason, then fold to complete hand (spectator sees previous hand)
        client.post(
            f"/game/poker/{gid}/action",
            json={"action": "call", "reason": "I think they're bluffing"},
            headers=auth_header(first_key),
        )
        client.post(
            f"/game/poker/{gid}/action",
            json={"action": "fold"},
            headers=auth_header(second_key),
        )
        # Spectator should see hand 1 with reason visible
        spec = client.get(f"/game/poker/{gid}/spectator").json()
        reasons = [a["reason"] for a in spec["recent_actions"] if a.get("reason")]
        assert "I think they're bluffing" in reasons


# ── Streams ────────────────────────────────────────────

class TestStreams:
    def _setup_started_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b

    def test_create_stream(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        resp = client.post(
            f"/game/{gid}/streams",
            json={"title": "Alice's Stream"},
            headers=auth_header(key),
        )
        assert resp.status_code == 200
        assert resp.json()["stream_id"] >= 1

    def test_create_stream_requires_auth(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/{gid}/streams", json={"title": "No auth"})
        assert resp.status_code == 401

    def test_create_stream_game_not_found(self, client):
        key = register_account(client, "Alice")
        resp = client.post(
            "/game/999/streams",
            json={"title": "Test"},
            headers=auth_header(key),
        )
        assert resp.status_code == 404

    def test_create_stream_empty_title(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        resp = client.post(
            f"/game/{gid}/streams",
            json={"title": "   "},
            headers=auth_header(key),
        )
        assert resp.status_code == 400

    def test_create_stream_title_too_long(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        resp = client.post(
            f"/game/{gid}/streams",
            json={"title": "x" * 101},
            headers=auth_header(key),
        )
        assert resp.status_code == 400

    def test_duplicate_host_per_game_rejected(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        client.post(
            f"/game/{gid}/streams",
            json={"title": "First"},
            headers=auth_header(key),
        )
        resp = client.post(
            f"/game/{gid}/streams",
            json={"title": "Second"},
            headers=auth_header(key),
        )
        assert resp.status_code == 400

    def test_stream_commentate(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        sid = client.post(
            f"/game/{gid}/streams",
            json={"title": "Alice's Stream"},
            headers=auth_header(key),
        ).json()["stream_id"]

        resp = client.post(
            f"/stream/{sid}/commentate",
            json={"text": "What a play!"},
            headers=auth_header(key),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_stream_commentate_requires_auth(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        sid = client.post(
            f"/game/{gid}/streams",
            json={"title": "Test"},
            headers=auth_header(key),
        ).json()["stream_id"]

        resp = client.post(f"/stream/{sid}/commentate", json={"text": "No auth"})
        assert resp.status_code == 401

    def test_stream_commentate_only_host(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        sid = client.post(
            f"/game/{gid}/streams",
            json={"title": "Alice's Stream"},
            headers=auth_header(key_a),
        ).json()["stream_id"]

        resp = client.post(
            f"/stream/{sid}/commentate",
            json={"text": "I'm not the host"},
            headers=auth_header(key_b),
        )
        assert resp.status_code == 403

    def test_stream_commentate_not_found(self, client):
        key = register_account(client, "Alice")
        resp = client.post(
            "/stream/999/commentate",
            json={"text": "No stream"},
            headers=auth_header(key),
        )
        assert resp.status_code == 404

    def test_stream_data(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        sid = client.post(
            f"/game/{gid}/streams",
            json={"title": "Alice's Stream"},
            headers=auth_header(key),
        ).json()["stream_id"]

        client.post(
            f"/stream/{sid}/commentate",
            json={"text": "Hello viewers!"},
            headers=auth_header(key),
        )

        resp = client.get(f"/stream/{sid}/data")
        assert resp.status_code == 200
        data = resp.json()
        assert data["commentary_text"] == "Hello viewers!"
        assert data["stream_id"] == sid
        assert data["stream_title"] == "Alice's Stream"
        assert data["stream_host"] == "Alice"

    def test_stream_data_no_commentary(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        sid = client.post(
            f"/game/{gid}/streams",
            json={"title": "Silent Stream"},
            headers=auth_header(key),
        ).json()["stream_id"]

        resp = client.get(f"/stream/{sid}/data")
        assert resp.status_code == 200
        data = resp.json()
        assert data["commentary_text"] is None
        assert data["stream_id"] == sid

    def test_stream_data_not_found(self, client):
        resp = client.get("/stream/999/data")
        assert resp.status_code == 404

    def test_stream_data_includes_game_state(self, client):
        """Stream data should include the game's spectator data."""
        gid, key_a, key_b = self._setup_started_game(client)

        # Complete hand 1
        s1 = client.get(f"/game/poker/{gid}/state", headers=auth_header(key_a)).json()
        first_key = key_a if s1["is_your_turn"] else key_b
        client.post(f"/game/poker/{gid}/action", json={"action": "fold"}, headers=auth_header(first_key))

        # Create a stream
        key_c = register_account(client, "Charlie")
        sid = client.post(
            f"/game/{gid}/streams",
            json={"title": "Charlie's Cast"},
            headers=auth_header(key_c),
        ).json()["stream_id"]

        resp = client.get(f"/stream/{sid}/data")
        data = resp.json()
        # Should have game data from previous hand
        assert data["hand_number"] == 1
        assert data["phase"] == "complete"
        assert len(data["players"]) == 2

    def test_multiple_streams_independent_commentary(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        sid_a = client.post(
            f"/game/{gid}/streams",
            json={"title": "Alice's Stream"},
            headers=auth_header(key_a),
        ).json()["stream_id"]
        sid_b = client.post(
            f"/game/{gid}/streams",
            json={"title": "Bob's Stream"},
            headers=auth_header(key_b),
        ).json()["stream_id"]

        client.post(f"/stream/{sid_a}/commentate", json={"text": "Alice says hi"}, headers=auth_header(key_a))
        client.post(f"/stream/{sid_b}/commentate", json={"text": "Bob says hey"}, headers=auth_header(key_b))

        resp_a = client.get(f"/stream/{sid_a}/data")
        resp_b = client.get(f"/stream/{sid_b}/data")
        assert resp_a.json()["commentary_text"] == "Alice says hi"
        assert resp_b.json()["commentary_text"] == "Bob says hey"

    def test_raw_spectator_has_no_commentary(self, client):
        """The base spectator endpoint should always have commentary_text=None."""
        gid = create_game(client)
        key = register_account(client, "Alice")
        resp = client.post(
            f"/game/{gid}/streams",
            json={"title": "Alice's Stream"},
            headers=auth_header(key),
        )
        sid = resp.json()["stream_id"]
        client.post(f"/stream/{sid}/commentate", json={"text": "Hello!"}, headers=auth_header(key))

        # Raw spectator should have no commentary
        resp = client.get(f"/game/poker/{gid}/spectator")
        assert resp.json()["commentary_text"] is None


# ── Escrow Integration ──────────────────────────────────

class TestResign:
    def _setup_3player_game(self, client):
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        key_c = register_account(client, "Charlie")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        join_game(client, gid, key_c)
        client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        return gid, key_a, key_b, key_c

    def test_resign_requires_auth(self, client):
        gid = create_game(client)
        resp = client.post(f"/game/poker/{gid}/resign")
        assert resp.status_code == 401

    def test_resign_requires_player(self, client):
        gid, key_a, key_b, _ = self._setup_3player_game(client)
        key_d = register_account(client, "Dave")
        resp = client.post(f"/game/poker/{gid}/resign", headers=auth_header(key_d))
        assert resp.status_code == 404

    def test_resign_success(self, client):
        gid, _, key_b, _ = self._setup_3player_game(client)
        resp = client.post(f"/game/poker/{gid}/resign", headers=auth_header(key_b))
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "Resigned from game"

    def test_resign_visible_in_spectator(self, client):
        gid, key_a, key_b, key_c = self._setup_3player_game(client)
        client.post(f"/game/poker/{gid}/resign", headers=auth_header(key_b))
        spec = client.get(f"/game/poker/{gid}/spectator").json()
        bob = next(p for p in spec["players"] if p["name"] == "Bob")
        assert bob["is_resigned"] is True

    def test_resign_before_start(self, client):
        gid = create_game(client)
        key = register_account(client, "Alice")
        join_game(client, gid, key)
        resp = client.post(f"/game/poker/{gid}/resign", headers=auth_header(key))
        assert resp.status_code == 400
        assert "not started" in resp.json()["detail"].lower()


class TestEscrowGameCreation:
    """Test funded game creation, joining, and lifecycle."""

    def test_create_funded_game(self, client):
        resp = client.post("/game/poker/games", json={
            "max_players": 2,
            "token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "buy_in": 100_000_000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_players"] == 2
        assert data["token"] == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        assert data["buy_in"] == 100_000_000

    def test_create_free_game_defaults(self, client):
        """Creating a game with default values (no token, buy_in=0)."""
        resp = client.post("/game/poker/games", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_players"] == 0
        assert data["token"] is None
        assert data["buy_in"] == 0

    def test_join_funded_game_requires_wallet(self, client):
        resp = client.post("/game/poker/games", json={
            "max_players": 2,
            "token": "0x0000000000000000000000000000000000000001",
            "buy_in": 100,
        })
        gid = resp.json()["game_id"]

        key = register_account(client, "Alice")
        # No wallet_address provided
        resp = client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": None},
            headers=auth_header(key),
        )
        assert resp.status_code == 400
        assert "Wallet address required" in resp.json()["detail"]

    def test_join_funded_game_with_wallet(self, client):
        resp = client.post("/game/poker/games", json={
            "max_players": 2,
            "token": "0x0000000000000000000000000000000000000001",
            "buy_in": 100,
        })
        gid = resp.json()["game_id"]

        key = register_account(client, "Alice")
        resp = client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"},
            headers=auth_header(key),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Alice"

    def test_join_free_game_no_wallet_needed(self, client):
        """Free games (buy_in=0) don't require wallet."""
        gid = create_game(client)
        key = register_account(client, "Alice")
        resp = client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": None},
            headers=auth_header(key),
        )
        assert resp.status_code == 200

    def test_join_full_game_rejected(self, client):
        resp = client.post("/game/poker/games", json={"max_players": 2})
        gid = resp.json()["game_id"]

        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        key_c = register_account(client, "Charlie")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)

        resp = client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": None},
            headers=auth_header(key_c),
        )
        assert resp.status_code == 400
        assert "full" in resp.json()["detail"].lower()

    def test_start_funded_game_before_funding_rejected(self, client):
        resp = client.post("/game/poker/games", json={
            "max_players": 2,
            "token": "0x0000000000000000000000000000000000000001",
            "buy_in": 100,
        })
        gid = resp.json()["game_id"]

        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"},
            headers=auth_header(key_a),
        )
        client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"},
            headers=auth_header(key_b),
        )

        resp = client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        assert resp.status_code == 400
        assert "Deposits not confirmed" in resp.json()["detail"]

    def test_start_free_game_works(self, client):
        """Free games can be started without funding."""
        gid = create_game(client)
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")
        join_game(client, gid, key_a)
        join_game(client, gid, key_b)
        resp = client.post(f"/game/poker/{gid}/start", headers=auth_header(key_a))
        assert resp.status_code == 200

    def test_duplicate_wallet_rejected(self, client):
        """Two players cannot join with the same wallet address."""
        resp = client.post("/game/poker/games", json={
            "max_players": 3,
            "token": "0x0000000000000000000000000000000000000001",
            "buy_in": 100,
        })
        gid = resp.json()["game_id"]

        wallet = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")

        client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": wallet},
            headers=auth_header(key_a),
        )
        resp = client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": wallet},
            headers=auth_header(key_b),
        )
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"].lower()

    def test_duplicate_wallet_case_insensitive(self, client):
        """Wallet address duplicate check is case-insensitive."""
        resp = client.post("/game/poker/games", json={
            "max_players": 3,
            "token": "0x0000000000000000000000000000000000000001",
            "buy_in": 100,
        })
        gid = resp.json()["game_id"]

        key_a = register_account(client, "Alice")
        key_b = register_account(client, "Bob")

        client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"},
            headers=auth_header(key_a),
        )
        resp = client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"},
            headers=auth_header(key_b),
        )
        assert resp.status_code == 400


class TestEscrowEndpoints:
    """Test escrow, funding, and settlement endpoints."""

    def test_escrow_not_funded_game(self, client):
        gid = create_game(client)
        resp = client.get(f"/game/poker/{gid}/escrow")
        assert resp.status_code == 400
        assert "on-chain" in resp.json()["detail"].lower()

    def test_escrow_not_full(self, client):
        resp = client.post("/game/poker/games", json={
            "max_players": 2,
            "token": "0x0000000000000000000000000000000000000001",
            "buy_in": 100,
        })
        gid = resp.json()["game_id"]

        key = register_account(client, "Alice")
        client.post(
            f"/game/poker/{gid}/join",
            json={"wallet_address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"},
            headers=auth_header(key),
        )

        resp = client.get(f"/game/poker/{gid}/escrow")
        assert resp.status_code == 400
        assert "not full" in resp.json()["detail"].lower()

    def test_funding_not_funded_game(self, client):
        gid = create_game(client)
        resp = client.get(f"/game/poker/{gid}/funding")
        assert resp.status_code == 400

    def test_funding_no_escrow_configured(self, client):
        resp = client.post("/game/poker/games", json={
            "max_players": 2,
            "token": "0x0000000000000000000000000000000000000001",
            "buy_in": 100,
        })
        gid = resp.json()["game_id"]

        resp = client.get(f"/game/poker/{gid}/funding")
        assert resp.status_code == 400
        assert "Escrow not yet configured" in resp.json()["detail"]

    def test_settlement_not_funded_game(self, client):
        gid = create_game(client)
        resp = client.get(f"/game/poker/{gid}/settlement")
        assert resp.status_code == 400

    def test_settlement_game_not_over(self, client):
        resp = client.post("/game/poker/games", json={
            "max_players": 2,
            "token": "0x0000000000000000000000000000000000000001",
            "buy_in": 100,
        })
        gid = resp.json()["game_id"]

        resp = client.get(f"/game/poker/{gid}/settlement")
        assert resp.status_code == 400
        assert "not over" in resp.json()["detail"].lower()

    def test_settlement_no_escrow(self, client):
        """Settlement with game over but no escrow configured."""
        resp = client.post("/game/poker/games", json={
            "max_players": 2,
            "token": "0x0000000000000000000000000000000000000001",
            "buy_in": 100,
        })
        gid = resp.json()["game_id"]

        # Manually set game_over to bypass normal flow for this edge case
        game = game_module.manager.get_game(gid)
        game.game_over = True

        resp = client.get(f"/game/poker/{gid}/settlement")
        assert resp.status_code == 400
        assert "Escrow not configured" in resp.json()["detail"]
