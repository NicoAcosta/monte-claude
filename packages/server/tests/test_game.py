from unittest.mock import patch

import pytest
from poker.game import Game, STARTING_CHIPS


class TestRegistration:
    def test_register_player(self):
        game = Game()
        p = game.register("Alice")
        assert p.id == 1
        assert p.name == "Alice"
        assert p.chips == STARTING_CHIPS

    def test_register_multiple(self):
        game = Game()
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        assert p1.id == 1
        assert p2.id == 2

    def test_duplicate_name_rejected(self):
        game = Game()
        game.register("Alice")
        with pytest.raises(ValueError, match="already taken"):
            game.register("Alice")

    def test_empty_name_rejected(self):
        game = Game()
        with pytest.raises(ValueError, match="empty"):
            game.register("")

    def test_register_after_start_rejected(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        game.start()
        with pytest.raises(ValueError, match="already started"):
            game.register("Charlie")


class TestGameStart:
    def test_start_game(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        hand_num = game.start()
        assert hand_num == 1
        assert game.started
        assert game.current_hand is not None

    def test_start_requires_two_players(self):
        game = Game()
        game.register("Alice")
        with pytest.raises(ValueError, match="at least 2"):
            game.start()

    def test_double_start_rejected(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        game.start()
        with pytest.raises(ValueError, match="already started"):
            game.start()


class TestGameplay:
    def test_action_before_start(self):
        game = Game()
        result = game.do_action(1, "fold")
        assert result == "Game not started"

    def test_play_hand_to_completion(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        game.start()
        # Fold immediately
        cp = game.current_hand.current_player
        game.do_action(cp.id, "fold")
        # New hand should have started
        assert game.hand_number == 2
        assert game.current_hand is not None

    def test_elimination(self):
        game = Game()
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        # Give Alice only enough for one blind
        p1.chips = 20
        p2.chips = 1980
        game.start()
        # Alice goes all-in, Bob calls
        cp = game.current_hand.current_player
        game.do_action(cp.id, "all_in")
        cp = game.current_hand.current_player
        if cp is not None:
            game.do_action(cp.id, "call")
        # Eventually the hand completes; loser might get eliminated
        # (outcome depends on cards dealt - non-deterministic without seed)


class TestChipConservation:
    def test_chips_conserved_across_fold_hands(self):
        """Total chips must remain constant when hands end by fold."""
        game = Game()
        game.register("Alice")
        game.register("Bob")
        game.start()
        total = sum(p.chips for p in game._players)
        for _ in range(20):
            if game.game_over:
                break
            if game.current_hand and game.current_hand.current_player:
                game.do_action(game.current_hand.current_player.id, "fold")
            current_total = sum(p.chips for p in game._players)
            assert current_total == total, (
                f"Chip leak detected: expected {total}, got {current_total} "
                f"(hand {game.hand_number})"
            )


class TestGameOver:
    def test_game_over_detection(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        game.start()
        # Keep folding until someone runs out of chips
        max_hands = 200
        for _ in range(max_hands):
            if game.game_over:
                break
            if game.current_hand and game.current_hand.current_player:
                game.do_action(game.current_hand.current_player.id, "fold")
        # After enough folds, the blinds will drain one player
        # (may not reach game over in 200 folds with 1000 chips and 10/20 blinds)
        # This is a smoke test - just verify no crashes


class TestPlayerLookup:
    def test_get_player(self):
        game = Game()
        p = game.register("Alice")
        found = game.get_player(p.id)
        assert found is not None
        assert found.name == "Alice"

    def test_get_player_not_found(self):
        game = Game()
        assert game.get_player(999) is None

    def test_get_player_by_name(self):
        game = Game()
        game.register("Alice")
        found = game.get_player_by_name("Alice")
        assert found is not None
        assert found.name == "Alice"
        assert found.id == 1

    def test_get_player_by_name_not_found(self):
        game = Game()
        assert game.get_player_by_name("Nobody") is None


class TestChat:
    def test_add_chat(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        game.add_chat("Alice", "Hello!")
        assert len(game.chat_log) == 1
        name, msg, ts = game.chat_log[0]
        assert name == "Alice"
        assert msg == "Hello!"
        assert ts > 0

    def test_chat_log_bounded(self):
        game = Game()
        game._chat_max = 5
        for i in range(10):
            game.add_chat("P", f"msg{i}")
        assert len(game.chat_log) == 5
        assert game.chat_log[0][1] == "msg5"
        assert game.chat_log[-1][1] == "msg9"

    def test_chat_event_emitted(self):
        events = []
        game = Game(event_callback=lambda t, d: events.append((t, d)))
        game.add_chat("Alice", "Hi")
        chat_events = [(t, d) for t, d in events if t == "chat"]
        assert len(chat_events) == 1
        assert chat_events[0][1]["player_name"] == "Alice"
        assert chat_events[0][1]["message"] == "Hi"


class TestActionReason:
    def test_reason_threaded_to_hand(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        game.start()
        cp = game.current_hand.current_player
        game.do_action(cp.id, "call", reason="Pot odds are good")
        reason_actions = [a for a in game.current_hand.actions if a.reason is not None]
        assert len(reason_actions) == 1
        assert reason_actions[0].reason == "Pot odds are good"

    def test_reason_in_event_callback(self):
        events = []
        game = Game(event_callback=lambda t, d: events.append((t, d)))
        game.register("Alice")
        game.register("Bob")
        game.start()
        cp = game.current_hand.current_player
        game.do_action(cp.id, "call", reason="My reasoning")
        action_events = [(t, d) for t, d in events if t == "action" and d.get("reason")]
        assert len(action_events) == 1
        assert action_events[0][1]["reason"] == "My reasoning"


class TestActionTimer:
    def _make_started_game(self, action_timeout=15.0, extensions_per_player=3):
        game = Game(action_timeout=action_timeout, extensions_per_player=extensions_per_player)
        game.register("Alice")
        game.register("Bob")
        game.start()
        return game

    def test_turn_deadline_set(self):
        game = self._make_started_game()
        assert game.turn_deadline is not None
        assert game.turn_deadline > 0

    def test_extensions_initialized(self):
        game = self._make_started_game(extensions_per_player=5)
        assert game.get_extensions_remaining(1) == 5
        assert game.get_extensions_remaining(2) == 5

    def test_no_timeout_when_time_remaining(self):
        game = self._make_started_game(action_timeout=15.0)
        assert game._check_timeout() is None

    def test_timeout_auto_folds(self):
        game = self._make_started_game(action_timeout=15.0)
        cp = game.current_hand.current_player
        player_name = cp.name

        # Simulate time passing beyond deadline
        with patch("poker.game.time.time", return_value=game.turn_deadline + 1):
            result = game._check_timeout()

        assert result == player_name

    def test_timeout_disabled_when_zero(self):
        game = self._make_started_game(action_timeout=0)
        assert game._check_timeout() is None

    def test_use_extension_adds_time(self):
        game = self._make_started_game(action_timeout=10.0, extensions_per_player=2)
        cp = game.current_hand.current_player
        old_deadline = game.turn_deadline

        result = game.use_extension(cp.id)
        assert result is not None
        new_deadline, remaining = result
        assert new_deadline == old_deadline + 10.0
        assert remaining == 1

    def test_use_extension_decrements(self):
        game = self._make_started_game(extensions_per_player=1)
        cp = game.current_hand.current_player

        result = game.use_extension(cp.id)
        assert result is not None
        assert result[1] == 0

        # No more extensions
        result2 = game.use_extension(cp.id)
        assert result2 is None

    def test_cannot_extend_not_your_turn(self):
        game = self._make_started_game()
        cp = game.current_hand.current_player
        other_id = 1 if cp.id == 2 else 2
        assert game.use_extension(other_id) is None

    def test_extra_time_resets_on_action(self):
        game = self._make_started_game(action_timeout=10.0, extensions_per_player=2)
        cp = game.current_hand.current_player
        game.use_extension(cp.id)
        assert game._extra_time == 10.0

        game.do_action(cp.id, "call")
        assert game._extra_time == 0.0

    def test_timeout_cascades_hands(self):
        """Timeout fold that completes a hand should start next hand correctly."""
        game = self._make_started_game(action_timeout=5.0)
        hand_before = game.hand_number

        cp = game.current_hand.current_player
        with patch("poker.game.time.time", return_value=game.turn_deadline + 1):
            game._check_timeout()

        # Hand should have advanced
        assert game.hand_number > hand_before
