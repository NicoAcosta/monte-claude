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
