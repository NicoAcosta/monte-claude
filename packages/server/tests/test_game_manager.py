import asyncio

import pytest

from core.event_bus import GameEventBus
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
        assert isinstance(game_id, str) and len(game_id) == 32
        assert game is not None
        assert config is not None

    def test_create_game_unique_ids(self):
        mgr = _make_manager()
        id1, _, _ = mgr.create_game()
        id2, _, _ = mgr.create_game()
        assert isinstance(id1, str) and len(id1) == 32
        assert isinstance(id2, str) and len(id2) == 32
        assert id1 != id2

    def test_get_game_exists(self):
        mgr = _make_manager()
        game_id, game, _ = mgr.create_game()
        assert mgr.get_game(game_id) is game

    def test_get_game_missing(self):
        mgr = _make_manager()
        assert mgr.get_game("nonexistent") is None

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
            s.id = "modified"
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


class TestGameManagerEventBus:
    """Test event bus integration with GameManager."""

    @pytest.mark.asyncio
    async def test_start_publishes_events(self):
        """Starting a game publishes hand_started and other events to the bus."""
        bus = GameEventBus()
        mgr = _make_manager(event_bus=bus)
        game_id, game, _ = mgr.create_game()
        game.register("Alice")
        game.register("Bob")

        sub = bus.subscribe(game_id)
        game.start()

        # game.start() fires events through the event callback
        # (hand_started, cards_dealt, action for blinds, etc.)
        events = []
        while True:
            ev = sub.get_nowait()
            if ev is None:
                break
            events.append(ev)

        event_types = [e[0] for e in events]
        assert "hand_started" in event_types
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_action_publishes_to_bus(self):
        """do_action() events flow through the bus."""
        bus = GameEventBus()
        mgr = _make_manager(event_bus=bus)
        game_id, game, _ = mgr.create_game()
        game.register("Alice")
        game.register("Bob")
        game.start()

        sub = bus.subscribe(game_id)

        # Find who is the current player and fold
        hand = game.current_hand
        current = hand.current_player
        game.do_action(current.id, "fold")

        events = []
        while True:
            ev = sub.get_nowait()
            if ev is None:
                break
            events.append(ev)

        assert len(events) > 0
        event_types = [e[0] for e in events]
        assert "action" in event_types

    @pytest.mark.asyncio
    async def test_no_bus_does_not_error(self):
        """Manager works fine without an event bus (backward compat)."""
        mgr = _make_manager()  # no event_bus
        game_id, game, _ = mgr.create_game()
        game.register("Alice")
        game.register("Bob")
        game.start()  # Should not raise

    def test_event_bus_property(self):
        bus = GameEventBus()
        mgr = _make_manager(event_bus=bus)
        assert mgr.event_bus is bus

    def test_event_bus_property_none(self):
        mgr = _make_manager()
        assert mgr.event_bus is None

    @pytest.mark.asyncio
    async def test_cleanup_completed_cleans_bus(self):
        """cleanup_completed() also cleans up bus subscribers for removed games."""
        bus = GameEventBus()
        mgr = _make_manager(event_bus=bus)

        # Create multiple games and force them to game_over via all-in
        game_ids = []
        for i in range(8):
            gid, game, _ = mgr.create_game()
            game.register(f"Cx{i}a")
            game.register(f"Cx{i}b")
            game.start()
            # Force quick game over: first player goes all-in, second calls
            hand = game.current_hand
            cp = hand.current_player
            game.do_action(cp.id, "raise", 1000)
            hand = game.current_hand
            if hand and hand.current_player:
                game.do_action(hand.current_player.id, "call")
            # After all-in + call, one player busts and game is over
            assert game.game_over, f"Game {i} should be over after all-in showdown"
            game_ids.append(gid)

        # Subscribe to some games
        bus.subscribe(game_ids[0])
        bus.subscribe(game_ids[1])

        # Cleanup should remove old games (keeping 5 recent)
        removed = mgr.cleanup_completed(keep_recent=5)
        assert removed == 3  # 8 total - 5 kept = 3 removed

        # Subscribers for removed games should be cleaned up
        # game_ids[0..2] were removed (oldest 3)
        assert bus.subscriber_count(game_ids[0]) == 0
        assert bus.subscriber_count(game_ids[1]) == 0
        assert bus.subscriber_count(game_ids[2]) == 0
