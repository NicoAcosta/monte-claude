import json

from core.account_store import AccountStore
from core.db import get_pool
from poker.game import Game
from core.game_recorder import GameRecorder
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore
from poker.recorder import make_poker_materializer


def _make_recorder(game_id=1):
    pool = get_pool()
    event_store = GameEventStore(pool)
    summary_store = HandSummaryStore(pool)
    stats_store = PlayerStatsStore(pool)
    poker_materializer = make_poker_materializer(summary_store)
    recorder = GameRecorder(game_id, event_store, stats_store, summary_materializer=poker_materializer)
    return recorder, event_store, summary_store, stats_store


def _ensure_accounts(*names):
    """Create accounts for player names used in recorder tests."""
    pool = get_pool()
    store = AccountStore(pool)
    for name in names:
        try:
            store.create_account(name)
        except ValueError:
            pass


class TestGameRecorderIntegration:
    def test_fold_records_events(self):
        _ensure_accounts("Alice", "Bob")
        recorder, event_store, summary_store, stats_store = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        # Fold to end the hand
        cp = game.current_hand.current_player
        game.do_action(cp.id, "fold")

        events = event_store.get_by_game(1)
        event_types = [e.event_type for e in events]

        # Must have: hand_started, cards_dealt (x2), actions (blinds + fold),
        # hand_completed, hand_started (next hand)
        assert "hand_started" in event_types
        assert "cards_dealt" in event_types
        assert "action" in event_types
        assert "hand_completed" in event_types

    def test_hand_summary_created_on_completion(self):
        _ensure_accounts("Alice", "Bob")
        recorder, event_store, summary_store, stats_store = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        cp = game.current_hand.current_player
        game.do_action(cp.id, "fold")

        summaries = summary_store.get_by_game(1)
        assert len(summaries) >= 1
        assert summaries[0].hand_number == 1
        assert summaries[0].pot > 0

    def test_player_stats_updated(self):
        _ensure_accounts("Alice", "Bob")
        recorder, event_store, summary_store, stats_store = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        cp = game.current_hand.current_player
        game.do_action(cp.id, "fold")

        alice_stats = stats_store.get("Alice")
        bob_stats = stats_store.get("Bob")
        assert alice_stats is not None
        assert bob_stats is not None
        assert alice_stats.hands_played + bob_stats.hands_played >= 2

    def test_multiple_hands_accumulate(self):
        _ensure_accounts("Alice", "Bob")
        recorder, event_store, summary_store, stats_store = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        # Play 3 hands by folding
        for _ in range(3):
            if game.game_over or game.current_hand is None:
                break
            cp = game.current_hand.current_player
            if cp is not None:
                game.do_action(cp.id, "fold")

        summaries = summary_store.get_by_game(1)
        assert len(summaries) >= 3

        alice_stats = stats_store.get("Alice")
        bob_stats = stats_store.get("Bob")
        assert alice_stats.hands_played >= 3
        assert bob_stats.hands_played >= 3

    def test_events_have_sequential_order(self):
        _ensure_accounts("Alice", "Bob")
        recorder, event_store, summary_store, stats_store = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        cp = game.current_hand.current_player
        game.do_action(cp.id, "fold")

        events = event_store.get_by_game(1)
        sequences = [e.sequence for e in events]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)  # all unique

    def test_community_dealt_events_on_full_hand(self):
        _ensure_accounts("Alice", "Bob")
        recorder, event_store, summary_store, stats_store = _make_recorder()
        # Use a deterministic seed so we can control the hand
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        # Play through: call preflop, check each round
        hand = game.current_hand
        for _ in range(20):  # safety limit
            if hand is None or hand.is_complete:
                break
            cp = hand.current_player
            if cp is None:
                break
            if hand.phase == "preflop" and cp.current_bet < hand.current_bet:
                game.do_action(cp.id, "call")
            else:
                result = game.do_action(cp.id, "check")
                if result != "ok":
                    game.do_action(cp.id, "call")
            hand = game.current_hand

        events = event_store.get_by_game(1)
        community_events = [e for e in events if e.event_type == "community_dealt"]
        # Should have flop, turn, river = 3 community_dealt events for hand 1
        hand1_community = [e for e in community_events if e.hand_number == 1]
        assert len(hand1_community) == 3

        phases = [json.loads(e.data)["phase"] for e in hand1_community]
        assert phases == ["flop", "turn", "river"]

    def test_game_over_event(self):
        _ensure_accounts("Alice", "Bob")
        recorder, event_store, summary_store, stats_store = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        # Give Alice very few chips so game ends fast
        p1.chips = 30
        p2.chips = 1970
        game.start()

        for _ in range(100):
            if game.game_over:
                break
            if game.current_hand and game.current_hand.current_player:
                game.do_action(game.current_hand.current_player.id, "fold")

        if game.game_over:
            events = event_store.get_by_game(1)
            event_types = [e.event_type for e in events]
            assert "game_over" in event_types
            assert "player_eliminated" in event_types
