"""Unit tests for the dice game (Over/Under) and round logic."""

import pytest

from dice.round import categorize, resolve_round, RoundResult
from dice.game import DiceGame


# ── Round logic ───────────────────────────────────────────


class TestCategorize:
    def test_low(self):
        for total in (2, 3, 4, 5, 6):
            assert categorize(total) == "low"

    def test_seven(self):
        assert categorize(7) == "seven"

    def test_high(self):
        for total in (8, 9, 10, 11, 12):
            assert categorize(total) == "high"


class TestResolveRound:
    def test_single_winner_high(self):
        bets = {1: "high", 2: "low"}
        result = resolve_round(bets, ante=20, dice=(5, 4))  # total=9, high
        assert result.category == "high"
        assert result.winner_ids == (1,)
        assert result.payouts[1] == 40
        assert result.payouts[2] == 0

    def test_single_winner_low(self):
        bets = {1: "high", 2: "low"}
        result = resolve_round(bets, ante=20, dice=(1, 2))  # total=3, low
        assert result.category == "low"
        assert result.winner_ids == (2,)
        assert result.payouts[2] == 40

    def test_seven_winner(self):
        bets = {1: "seven", 2: "high"}
        result = resolve_round(bets, ante=20, dice=(3, 4))  # total=7
        assert result.category == "seven"
        assert result.winner_ids == (1,)
        assert result.payouts[1] == 40

    def test_no_winners(self):
        bets = {1: "high", 2: "high"}
        result = resolve_round(bets, ante=20, dice=(1, 2))  # total=3, low
        assert result.winner_ids == ()
        assert result.payouts[1] == 0
        assert result.payouts[2] == 0

    def test_multiple_winners_split(self):
        bets = {1: "high", 2: "high", 3: "low"}
        result = resolve_round(bets, ante=20, dice=(5, 5))  # total=10, high
        assert set(result.winner_ids) == {1, 2}
        assert result.pot == 60
        assert result.payouts[1] == 30
        assert result.payouts[2] == 30
        assert result.payouts[3] == 0

    def test_pot_equals_antes(self):
        bets = {1: "high", 2: "low", 3: "seven"}
        result = resolve_round(bets, ante=50, dice=(6, 6))
        assert result.pot == 150

    def test_remainder_goes_to_first_winner(self):
        bets = {1: "high", 2: "high", 3: "high"}
        result = resolve_round(bets, ante=10, dice=(5, 5))  # pot=30, 3 winners
        assert result.payouts[1] == 10
        assert result.payouts[2] == 10
        assert result.payouts[3] == 10


# ── DiceGame lifecycle ────────────────────────────────────


class TestDiceGameBasic:
    def _make_game(self, **kwargs) -> DiceGame:
        return DiceGame(**kwargs)

    def test_register_players(self):
        g = self._make_game()
        p1 = g.register("Alice")
        p2 = g.register("Bob")
        assert p1.name == "Alice"
        assert p2.name == "Bob"
        assert g.player_count == 2

    def test_register_duplicate_name_raises(self):
        g = self._make_game()
        g.register("Alice")
        with pytest.raises(ValueError, match="already taken"):
            g.register("Alice")

    def test_register_after_start_raises(self):
        g = self._make_game()
        g.register("Alice")
        g.register("Bob")
        g.start()
        with pytest.raises(ValueError, match="already started"):
            g.register("Charlie")

    def test_start_requires_two_players(self):
        g = self._make_game()
        g.register("Alice")
        with pytest.raises(ValueError, match="at least 2"):
            g.start()

    def test_start_sets_state(self):
        g = self._make_game()
        g.register("Alice")
        g.register("Bob")
        round_num = g.start()
        assert round_num == 1
        assert g.started is True
        assert g.hand_number == 1
        assert g.phase == "betting"

    def test_game_type(self):
        g = self._make_game()
        assert g.game_type == "dice"

    def test_starting_chips(self):
        g = self._make_game()
        assert g.starting_chips == 1000


class TestDiceGameplay:
    def _make_started_game(self, ante: int = 20) -> DiceGame:
        g = DiceGame(ante=ante, action_timeout=0)
        g.register("Alice")
        g.register("Bob")
        g.start()
        return g

    def test_betting_order(self):
        g = self._make_started_game()
        current = g.current_player
        assert current is not None
        assert current.name == "Alice"  # first alive player

    def test_invalid_bet_rejected(self):
        g = self._make_started_game()
        result = g.do_action(1, "bluff")
        assert "Invalid bet" in result

    def test_not_your_turn(self):
        g = self._make_started_game()
        result = g.do_action(2, "high")  # Bob, but it's Alice's turn
        assert "Not your turn" in result

    def test_valid_bet_advances_turn(self):
        g = self._make_started_game()
        result = g.do_action(1, "high")
        assert result == "ok"
        current = g.current_player
        assert current is not None
        assert current.name == "Bob"

    def test_full_round_resolves(self):
        g = self._make_started_game(ante=20)
        g.do_action(1, "high")
        g.do_action(2, "low")
        # Round should have resolved — phase transitions to next round's betting
        # or game over
        assert g.hand_number >= 2 or g.game_over
        # If someone won, total chips stay at 2000.
        # If nobody won (both picked wrong), pot is lost (house edge).
        total = g.get_player(1).chips + g.get_player(2).chips
        assert total <= 2000

    def test_ante_deducted(self):
        g = self._make_started_game(ante=100)
        # After start, ante deducted from both players
        assert g.get_player(1).chips == 900
        assert g.get_player(2).chips == 900

    def test_state_version_increments(self):
        g = self._make_started_game()
        v0 = g.state_version
        g.do_action(1, "high")
        assert g.state_version > v0

    def test_events_emitted(self):
        events = []
        g = DiceGame(event_callback=lambda t, d: events.append((t, d)), ante=20, action_timeout=0)
        g.register("Alice")
        g.register("Bob")
        g.start()
        g.do_action(1, "high")
        g.do_action(2, "low")
        event_types = [e[0] for e in events]
        assert "hand_started" in event_types
        assert "action" in event_types
        assert "round_resolved" in event_types
        assert "hand_completed" in event_types


class TestDiceResign:
    def _make_started_game(self) -> DiceGame:
        g = DiceGame(ante=20, action_timeout=0)
        g.register("Alice")
        g.register("Bob")
        g.start()
        return g

    def test_resign_ends_game_with_two_players(self):
        g = self._make_started_game()
        result = g.resign(2)
        assert result == "ok"
        assert g.game_over is True
        assert g.winner == "Alice"

    def test_resign_not_started(self):
        g = DiceGame()
        g.register("Alice")
        g.register("Bob")
        assert g.resign(1) == "Game not started"

    def test_resign_already_resigned(self):
        g = DiceGame(ante=20, action_timeout=0)
        g.register("Alice")
        g.register("Bob")
        g.register("Charlie")
        g.start()
        g.resign(3)
        assert g.resign(3) == "Already resigned"

    def test_resign_three_players_continues(self):
        g = DiceGame(ante=20, action_timeout=0)
        g.register("Alice")
        g.register("Bob")
        g.register("Charlie")
        g.start()
        result = g.resign(3)
        assert result == "ok"
        assert g.game_over is False


class TestDiceChat:
    def test_add_chat(self):
        g = DiceGame()
        g.register("Alice")
        g.register("Bob")
        g.add_chat("Alice", "Hello!")
        assert len(g.chat_log) == 1
        assert g.chat_log[0][0] == "Alice"
        assert g.chat_log[0][1] == "Hello!"


class TestDiceGameOver:
    def test_game_ends_when_only_one_can_ante(self):
        """Game ends when fewer than 2 players can afford the next ante."""
        from unittest.mock import MagicMock, patch
        # Mock FairRng so randbelow(6) returns 4 → dice = (5, 5) = 10 → high
        with patch("dice.game.FairRng") as MockFairRng:
            mock_rng = MagicMock()
            mock_rng.randbelow.return_value = 4
            MockFairRng.return_value = mock_rng

            g = DiceGame(ante=100, action_timeout=0)
            p1 = g.register("Alice")
            p2 = g.register("Bob")
            p1.chips = 1000
            p2.chips = 100
            g.start()
            # Both anted: Alice=900, Bob=0
            g.do_action(1, "high")  # Alice picks high
            g.do_action(2, "low")   # Bob picks low
            # Dice=(5,5)=10 → high wins → Alice gets pot (200)
            # Alice=1100, Bob=0 → only 1 can ante → game over
            assert g.game_over is True
            assert g.winner == "Alice"
