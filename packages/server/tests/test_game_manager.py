import pytest

from core.game_manager import GameManager, GameSummary
from poker.game import Game


def _make_manager(**kwargs) -> GameManager:
    mgr = GameManager(**kwargs)
    mgr.register_game_type("poker", Game)
    return mgr


class TestGameManager:
    def test_create_game_returns_id_and_game(self):
        mgr = _make_manager()
        game_id, game, config = mgr.create_game()
        assert game_id == 1
        assert game is not None
        assert config is not None

    def test_create_game_increments_ids(self):
        mgr = _make_manager()
        id1, _, _ = mgr.create_game()
        id2, _, _ = mgr.create_game()
        assert id1 == 1
        assert id2 == 2

    def test_get_game_exists(self):
        mgr = _make_manager()
        game_id, game, _ = mgr.create_game()
        assert mgr.get_game(game_id) is game

    def test_get_game_missing(self):
        mgr = _make_manager()
        assert mgr.get_game(999) is None

    def test_list_games_empty(self):
        mgr = _make_manager()
        assert mgr.list_games() == []

    def test_list_games_returns_summaries(self):
        mgr = _make_manager()
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
        mgr = _make_manager()
        _, game, _ = mgr.create_game()
        game.register("Alice")
        game.register("Bob")
        game.start()

        s = mgr.list_games()[0]
        assert s.started is True
        assert s.hand_number == 1

    def test_games_are_independent(self):
        mgr = _make_manager()
        _, g1, _ = mgr.create_game()
        _, g2, _ = mgr.create_game()
        g1.register("Alice")
        g2.register("Bob")
        assert g1.player_count == 1
        assert g2.player_count == 1
        assert mgr.list_games()[0].player_names == ("Alice",)
        assert mgr.list_games()[1].player_names == ("Bob",)

    def test_summary_is_frozen(self):
        mgr = _make_manager()
        mgr.create_game()
        s = mgr.list_games()[0]
        try:
            s.id = 999
            assert False, "Should not allow mutation"
        except AttributeError:
            pass


class TestGameTypeEnableDisable:
    def test_register_auto_enables(self):
        mgr = GameManager()
        mgr.register_game_type("poker", Game)
        assert mgr.is_game_type_enabled("poker")
        assert mgr.enabled_game_types == frozenset({"poker"})

    def test_disable_blocks_new_games(self):
        mgr = _make_manager()
        mgr.disable_game_type("poker")
        assert not mgr.is_game_type_enabled("poker")
        with pytest.raises(ValueError, match="currently disabled"):
            mgr.create_game(game_type="poker")

    def test_disable_keeps_existing_games(self):
        mgr = _make_manager()
        gid, game, _ = mgr.create_game()
        mgr.disable_game_type("poker")
        # Existing game still accessible and playable
        assert mgr.get_game(gid) is game
        assert mgr.get_config(gid) is not None

    def test_re_enable_allows_new_games(self):
        mgr = _make_manager()
        mgr.disable_game_type("poker")
        mgr.enable_game_type("poker")
        gid, game, _ = mgr.create_game()
        assert game is not None

    def test_enable_unknown_type_raises(self):
        mgr = GameManager()
        with pytest.raises(ValueError, match="Unknown game type"):
            mgr.enable_game_type("nonexistent")

    def test_disable_unknown_type_is_noop(self):
        mgr = GameManager()
        mgr.disable_game_type("nonexistent")  # no error

    def test_enabled_game_types_is_frozen(self):
        mgr = _make_manager()
        types = mgr.enabled_game_types
        assert isinstance(types, frozenset)

    def test_unknown_type_create_still_raises_unknown(self):
        """Unregistered types get 'Unknown' error, not 'disabled'."""
        mgr = _make_manager()
        with pytest.raises(ValueError, match="Unknown game type"):
            mgr.create_game(game_type="nonexistent")
