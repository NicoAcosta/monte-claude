import json

from core.db import get_pool
from poker.history_models import GameEvent, HandSummary, PlayerStats
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore


class TestGameEventStore:
    def test_append_and_query(self):
        store = GameEventStore(get_pool())
        event = GameEvent(
            game_id=1, event_type="action", timestamp=1000.0,
            hand_number=1, data=json.dumps({"player": "Alice", "action": "fold"}),
            sequence=1,
        )
        store.append(event)

        results = store.get_by_game(1)
        assert len(results) == 1
        assert results[0].event_type == "action"
        assert results[0].game_id == 1

    def test_filter_by_game_id(self):
        store = GameEventStore(get_pool())
        store.append(GameEvent(1, "action", 1000.0, 1, "{}", 1))
        store.append(GameEvent(2, "action", 1001.0, 1, "{}", 1))
        store.append(GameEvent(1, "action", 1002.0, 1, "{}", 2))

        assert len(store.get_by_game(1)) == 2
        assert len(store.get_by_game(2)) == 1
        assert len(store.get_by_game(3)) == 0

    def test_persistence_across_instances(self):
        pool = get_pool()
        store1 = GameEventStore(pool)
        store1.append(GameEvent(1, "action", 1000.0, 1, '{"x":1}', 1))

        store2 = GameEventStore(pool)
        results = store2.get_by_game(1)
        assert len(results) == 1
        assert results[0].data == '{"x":1}'


class TestHandSummaryStore:
    def test_append_and_query(self):
        store = HandSummaryStore(get_pool())
        summary = HandSummary(
            game_id=1, hand_number=1, dealer_id=1,
            player_ids=(1, 2), winner_ids=(1,),
            pot=100, community_cards=json.dumps(["Ah", "Kd", "Qs", "Jc", "Th"]),
            timestamp=1000.0,
        )
        store.append(summary)

        results = store.get_by_game(1)
        assert len(results) == 1
        assert results[0].winner_ids == (1,)
        assert results[0].player_ids == (1, 2)

    def test_persistence(self):
        pool = get_pool()
        store1 = HandSummaryStore(pool)
        store1.append(HandSummary(1, 1, 1, (1, 2), (2,), 200, "[]", 1000.0))

        store2 = HandSummaryStore(pool)
        results = store2.get_by_game(1)
        assert len(results) == 1
        assert results[0].pot == 200


class TestPlayerStatsStore:
    def test_update_and_get(self, make_account):
        make_account("Alice")
        store = PlayerStatsStore(get_pool())
        stats = PlayerStats("Alice", games_played=1, hands_played=5,
                            hands_won=2, total_winnings=100, biggest_pot_won=80)
        store.update(stats)

        result = store.get("Alice")
        assert result is not None
        assert result.hands_won == 2
        assert result.biggest_pot_won == 80

    def test_get_nonexistent(self):
        store = PlayerStatsStore(get_pool())
        assert store.get("Nobody") is None

    def test_update_from_hand(self, make_account):
        make_account("Alice")
        make_account("Bob")
        store = PlayerStatsStore(get_pool())
        store.update_from_hand(
            player_names=["Alice", "Bob"],
            winner_names=["Alice"],
            pot=100,
            chip_deltas={"Alice": 50, "Bob": -50},
        )

        alice = store.get("Alice")
        assert alice is not None
        assert alice.hands_played == 1
        assert alice.hands_won == 1
        assert alice.total_winnings == 50
        assert alice.biggest_pot_won == 100

        bob = store.get("Bob")
        assert bob is not None
        assert bob.hands_played == 1
        assert bob.hands_won == 0
        assert bob.total_winnings == -50

    def test_update_from_hand_accumulates(self, make_account):
        make_account("Alice")
        make_account("Bob")
        store = PlayerStatsStore(get_pool())
        store.update_from_hand(["Alice", "Bob"], ["Alice"], 100, {"Alice": 50, "Bob": -50})
        store.update_from_hand(["Alice", "Bob"], ["Bob"], 60, {"Alice": -30, "Bob": 30})

        alice = store.get("Alice")
        assert alice is not None
        assert alice.hands_played == 2
        assert alice.hands_won == 1
        assert alice.total_winnings == 20  # 50 + (-30)

    def test_increment_games_played(self, make_account):
        make_account("Alice")
        make_account("Bob")
        store = PlayerStatsStore(get_pool())
        store.increment_games_played(["Alice", "Bob"])

        assert store.get("Alice").games_played == 1
        assert store.get("Bob").games_played == 1

        store.increment_games_played(["Alice"])
        assert store.get("Alice").games_played == 2
        assert store.get("Bob").games_played == 1

    def test_persistence(self, make_account):
        make_account("Alice")
        pool = get_pool()
        store1 = PlayerStatsStore(pool)
        store1.update(PlayerStats("Alice", 1, 5, 2, 100, 80))

        store2 = PlayerStatsStore(pool)
        result = store2.get("Alice")
        assert result is not None
        assert result.total_winnings == 100
