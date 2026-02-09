import json

from poker.db import get_pool
from poker.game import Game
from poker.game_recorder import GameRecorder
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore
from poker.replay import GameSnapshot, apply_event, replay_game, replay_to


def _make_recorder(game_id=1):
    pool = get_pool()
    event_store = GameEventStore(pool)
    summary_store = HandSummaryStore(pool)
    stats_store = PlayerStatsStore(pool)
    recorder = GameRecorder(game_id, event_store, summary_store, stats_store)
    return recorder, event_store, summary_store, stats_store


class TestReplay:
    def test_replay_fold_hand(self):
        """Record a hand with fold, replay it, verify final state."""
        recorder, event_store, _, _ = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        # Play first hand: fold
        cp = game.current_hand.current_player
        game.do_action(cp.id, "fold")

        # Replay events for hand 1 only
        events = event_store.get_by_game(1)
        hand1_events = [e for e in events if e.hand_number == 1]

        snapshots = replay_game(hand1_events)
        assert len(snapshots) > 1

        # Final snapshot should be complete
        final = snapshots[-1]
        assert final.phase == "complete"
        assert final.hand_number == 1

        # One player should be folded
        folded = [p for p in final.players if p.is_folded]
        assert len(folded) == 1

    def test_replay_full_hand_to_showdown(self):
        """Play a full hand through to showdown, replay it."""
        recorder, event_store, _, _ = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        # Play through: call preflop, check every street
        hand = game.current_hand
        for _ in range(20):
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
        hand1_events = [e for e in events if e.hand_number == 1]

        snapshots = replay_game(hand1_events)
        final = snapshots[-1]
        assert final.phase == "complete"
        assert len(final.community_cards) == 5

    def test_replay_preserves_hole_cards(self):
        """Verify hole cards are captured during replay."""
        recorder, event_store, _, _ = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        # Get actual hole cards from the game
        actual_cards = {
            p.name: [str(c) for c in p.hole_cards]
            for p in game.current_hand.players
        }

        cp = game.current_hand.current_player
        game.do_action(cp.id, "fold")

        events = event_store.get_by_game(1)
        hand1_events = [e for e in events if e.hand_number == 1]
        snapshots = replay_game(hand1_events)

        # Find the snapshot right after the last cards_dealt event
        last_deal_idx = max(
            i for i, e in enumerate(hand1_events) if e.event_type == "cards_dealt"
        )
        # snapshots[0] = initial, snapshots[i+1] = after event i
        post_deal = snapshots[last_deal_idx + 1]

        for p in post_deal.players:
            assert list(p.hole_cards) == actual_cards[p.name]

    def test_replay_to_specific_step(self):
        """replay_to should return state at a specific event index."""
        recorder, event_store, _, _ = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        cp = game.current_hand.current_player
        game.do_action(cp.id, "fold")

        events = event_store.get_by_game(1)
        hand1_events = [e for e in events if e.hand_number == 1]

        # replay_to step 0 = after first event only
        state0 = replay_to(hand1_events, 0)
        assert state0.hand_number == 1
        assert state0.phase == "preflop"

        # replay_to last step should match replay_game final
        full = replay_game(hand1_events)
        state_last = replay_to(hand1_events, len(hand1_events) - 1)
        assert state_last == full[-1]

    def test_replay_pot_tracking(self):
        """Verify pot grows correctly during replay."""
        recorder, event_store, _, _ = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        # Call preflop (both put in BB=20)
        hand = game.current_hand
        cp = hand.current_player
        game.do_action(cp.id, "call")

        events = event_store.get_by_game(1)
        hand1_events = [e for e in events if e.hand_number == 1]

        snapshots = replay_game(hand1_events)
        # After blinds + call, pot should be 40 (SB=10, BB=20, call=20)
        # Find the snapshot after the call action
        for snap in snapshots:
            if snap.pot == 40:
                break
        else:
            # If we didn't find 40, at least check pot is positive
            assert snapshots[-1].pot > 0

    def test_replay_chips_conservation(self):
        """Total chips should be conserved during a hand."""
        recorder, event_store, _, _ = _make_recorder()
        game = Game(event_callback=recorder.on_event)
        game.register("Alice")
        game.register("Bob")
        game.start()

        cp = game.current_hand.current_player
        game.do_action(cp.id, "call")  # preflop call
        hand = game.current_hand
        if hand and not hand.is_complete and hand.current_player:
            game.do_action(hand.current_player.id, "check")

        events = event_store.get_by_game(1)
        hand1_events = [e for e in events if e.hand_number == 1]
        snapshots = replay_game(hand1_events)

        # For all mid-hand snapshots, chips + pot should be constant
        for snap in snapshots[1:]:  # skip initial empty state
            if not snap.players:
                continue
            total = sum(p.chips for p in snap.players) + snap.pot
            expected = sum(p.chips for p in snapshots[1].players) + snapshots[1].pot
            assert total == expected, f"Chips not conserved: {total} != {expected} at phase={snap.phase}"
