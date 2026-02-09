from core.game_manager import GameManager, GameSummary


class TestGameManager:
    def test_create_game_returns_id_and_game(self):
        mgr = GameManager()
        game_id, game, config = mgr.create_game()
        assert game_id == 1
        assert game is not None
        assert config is not None

    def test_create_game_increments_ids(self):
        mgr = GameManager()
        id1, _, _ = mgr.create_game()
        id2, _, _ = mgr.create_game()
        assert id1 == 1
        assert id2 == 2

    def test_get_game_exists(self):
        mgr = GameManager()
        game_id, game, _ = mgr.create_game()
        assert mgr.get_game(game_id) is game

    def test_get_game_missing(self):
        mgr = GameManager()
        assert mgr.get_game(999) is None

    def test_list_games_empty(self):
        mgr = GameManager()
        assert mgr.list_games() == []

    def test_list_games_returns_summaries(self):
        mgr = GameManager()
        gid, game, _ = mgr.create_game()
        game.register("Alice")
        game.register("Bob")

        summaries = mgr.list_games()
        assert len(summaries) == 1

        s = summaries[0]
        assert isinstance(s, GameSummary)
        assert s.id == gid
        assert s.player_count == 2
        assert s.player_names == ("Alice", "Bob")
        assert s.started is False
        assert s.game_over is False
        assert s.winner is None
        assert s.hand_number == 0

    def test_list_games_reflects_started(self):
        mgr = GameManager()
        _, game, _ = mgr.create_game()
        game.register("Alice")
        game.register("Bob")
        game.start()

        s = mgr.list_games()[0]
        assert s.started is True
        assert s.hand_number == 1

    def test_games_are_independent(self):
        mgr = GameManager()
        _, g1, _ = mgr.create_game()
        _, g2, _ = mgr.create_game()
        g1.register("Alice")
        g2.register("Bob")
        assert g1.player_count == 1
        assert g2.player_count == 1
        assert mgr.list_games()[0].player_names == ("Alice",)
        assert mgr.list_games()[1].player_names == ("Bob",)

    def test_summary_is_frozen(self):
        mgr = GameManager()
        mgr.create_game()
        s = mgr.list_games()[0]
        try:
            s.id = 999
            assert False, "Should not allow mutation"
        except AttributeError:
            pass
