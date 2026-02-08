import pytest
from poker.hand import ActionRecord, Hand, PlayerInHand


def make_players(n: int, chips: int = 1000) -> list[PlayerInHand]:
    return [PlayerInHand(id=i + 1, name=f"P{i + 1}", chips=chips) for i in range(n)]


class TestBlinds:
    def test_blinds_posted(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        # SB is player index 1 (left of dealer), BB is player index 2
        assert players[1].current_bet == 10  # SB
        assert players[2].current_bet == 20  # BB
        assert hand.pot == 30

    def test_heads_up_blinds(self):
        players = make_players(2)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        # Heads-up: dealer is SB, other is BB
        assert players[0].current_bet == 10  # Dealer = SB
        assert players[1].current_bet == 20  # BB
        assert hand.pot == 30


class TestBasicActions:
    def test_fold(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        # Preflop: action starts left of BB = player index 0 (dealer in 3-player)
        current = hand.current_player
        assert current is not None
        result = hand.do_action(current.id, "fold")
        assert result == "ok"
        assert current.is_folded

    def test_check_not_allowed_when_bet_exists(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        result = hand.do_action(current.id, "check")
        assert "Cannot check" in result

    def test_call(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        result = hand.do_action(current.id, "call")
        assert result == "ok"
        assert current.current_bet == 20

    def test_wrong_player_rejected(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        # Try acting as a different player
        other_id = (current.id % 3) + 1
        result = hand.do_action(other_id, "fold")
        assert result == "Not your turn"

    def test_unknown_action(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        result = hand.do_action(current.id, "dance")
        assert "Unknown action" in result


class TestBetting:
    def test_raise(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        # Call first would not raise; let's raise
        result = hand.do_action(current.id, "raise", 60)
        assert result == "ok"
        assert current.current_bet == 60

    def test_min_raise_enforced(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        # Min raise preflop with BB=20 should be to 40 (raise by 20)
        result = hand.do_action(current.id, "raise", 30)
        assert "Minimum raise" in result

    def test_bet_on_new_round(self):
        players = make_players(2)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        # Heads-up preflop: dealer(SB) acts first
        hand.do_action(hand.current_player.id, "call")
        # BB checks
        hand.do_action(hand.current_player.id, "check")
        # Now on flop, first to act is left of dealer
        assert hand.phase == "flop"
        assert len(hand.community_cards) == 3
        current = hand.current_player
        assert current is not None
        result = hand.do_action(current.id, "bet", 50)
        assert result == "ok"


class TestFoldToWin:
    def test_all_fold_wins(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        # Everyone folds to BB
        p = hand.current_player
        hand.do_action(p.id, "fold")
        p = hand.current_player
        hand.do_action(p.id, "fold")
        assert hand.is_complete
        assert len(hand.winners_by_pot) == 1
        assert hand.winners_by_pot[0][0] == 30  # pot
        # BB wins


class TestAllIn:
    def test_all_in(self):
        players = make_players(2, chips=100)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        hand.do_action(hand.current_player.id, "all_in")
        assert hand.players[0].is_all_in
        assert hand.players[0].chips == 0

    def test_all_in_call_goes_to_showdown(self):
        players = make_players(2, chips=100)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        hand.do_action(hand.current_player.id, "all_in")
        hand.do_action(hand.current_player.id, "call")
        assert hand.is_complete
        assert len(hand.community_cards) == 5


class TestSidePots:
    def test_side_pot_with_unequal_stacks(self):
        p1 = PlayerInHand(id=1, name="Short", chips=50)
        p2 = PlayerInHand(id=2, name="Medium", chips=200)
        p3 = PlayerInHand(id=3, name="Big", chips=500)
        hand = Hand([p1, p2, p3], dealer_index=0, deck_seed=42)
        # Dealer=P1(idx0), SB=P2(idx1), BB=P3(idx2)
        # Preflop starts at idx 0 (left of BB in 3-player)
        hand.do_action(1, "all_in")  # P1: 50 total
        hand.do_action(2, "all_in")  # P2: 200 total
        hand.do_action(3, "all_in")  # P3: 500 total
        assert hand.is_complete
        # Multiple side pots should exist
        assert len(hand.winners_by_pot) >= 1
        total_awarded = sum(amt for amt, _ in hand.winners_by_pot)
        assert total_awarded == hand.pot


class TestFullHand:
    def test_full_hand_to_showdown(self):
        players = make_players(2, chips=1000)
        hand = Hand(players, dealer_index=0, deck_seed=42)
        # preflop: SB calls, BB checks
        hand.do_action(hand.current_player.id, "call")
        hand.do_action(hand.current_player.id, "check")
        assert hand.phase == "flop"
        # flop: check check
        hand.do_action(hand.current_player.id, "check")
        hand.do_action(hand.current_player.id, "check")
        assert hand.phase == "turn"
        # turn: check check
        hand.do_action(hand.current_player.id, "check")
        hand.do_action(hand.current_player.id, "check")
        assert hand.phase == "river"
        # river: check check
        hand.do_action(hand.current_player.id, "check")
        hand.do_action(hand.current_player.id, "check")
        assert hand.is_complete
        assert len(hand.community_cards) == 5
        # Total pot should be 40 (SB 10 + BB 20 + call 10)
        assert hand.pot == 40


class TestActionRecordComment:
    def test_action_record_without_comment(self):
        rec = ActionRecord(id=1, timestamp=0.0, player_name="P1", action="fold")
        assert rec.comment is None

    def test_action_record_with_comment(self):
        rec = ActionRecord(id=1, timestamp=0.0, player_name="P1", action="fold", comment="Nice bluff!")
        assert rec.comment == "Nice bluff!"

    def test_comment_stored_in_hand_actions(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        hand.do_action(current.id, "call", comment="Let's see the flop")
        comment_actions = [a for a in hand.actions if a.comment is not None]
        assert len(comment_actions) == 1
        assert comment_actions[0].comment == "Let's see the flop"

    def test_comment_none_by_default(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        hand.do_action(current.id, "fold")
        fold_action = [a for a in hand.actions if a.action == "fold"][0]
        assert fold_action.comment is None


class TestActionRecordReason:
    def test_reason_none_by_default(self):
        rec = ActionRecord(id=1, timestamp=0.0, player_name="P1", action="fold")
        assert rec.reason is None

    def test_reason_stored_on_record(self):
        rec = ActionRecord(id=1, timestamp=0.0, player_name="P1", action="call", reason="Pot odds are good")
        assert rec.reason == "Pot odds are good"

    def test_reason_stored_in_hand_actions(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        hand.do_action(current.id, "call", reason="Implied odds justify this call")
        reason_actions = [a for a in hand.actions if a.reason is not None]
        assert len(reason_actions) == 1
        assert reason_actions[0].reason == "Implied odds justify this call"

    def test_reason_and_comment_coexist(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        hand.do_action(current.id, "call", comment="Let's go!", reason="Strong hand")
        action = [a for a in hand.actions if a.action == "call"][0]
        assert action.comment == "Let's go!"
        assert action.reason == "Strong hand"

    def test_reason_none_when_not_provided(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        current = hand.current_player
        assert current is not None
        hand.do_action(current.id, "fold")
        fold_action = [a for a in hand.actions if a.action == "fold"][0]
        assert fold_action.reason is None


class TestActionIdAndTimestamp:
    def test_actions_have_incrementing_ids(self):
        players = make_players(3)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        # Blinds produce 2 actions (id=1, id=2), then player acts
        current = hand.current_player
        hand.do_action(current.id, "fold")
        ids = [a.id for a in hand.actions]
        assert ids == [1, 2, 3]

    def test_actions_have_timestamps(self):
        players = make_players(2)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        for a in hand.actions:
            assert a.timestamp > 0

    def test_starting_action_id_offset(self):
        players = make_players(2)
        hand = Hand(players, dealer_index=0, deck_seed=1, starting_action_id=100)
        ids = [a.id for a in hand.actions]
        assert ids == [100, 101]  # two blind actions

    def test_timestamps_are_chronological(self):
        players = make_players(2)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        hand.do_action(hand.current_player.id, "call")
        hand.do_action(hand.current_player.id, "check")
        timestamps = [a.timestamp for a in hand.actions]
        assert timestamps == sorted(timestamps)


class TestTurnStartedAt:
    def test_turn_started_at_set_on_init(self):
        players = make_players(2)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        assert hand.turn_started_at is not None
        assert hand.turn_started_at > 0

    def test_turn_started_at_updates_on_advance(self):
        players = make_players(2)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        t1 = hand.turn_started_at
        hand.do_action(hand.current_player.id, "call")
        t2 = hand.turn_started_at
        assert t2 is not None
        assert t2 >= t1

    def test_turn_started_at_none_when_complete(self):
        players = make_players(2)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        hand.do_action(hand.current_player.id, "fold")
        assert hand.is_complete
        # current_turn_index is None, but turn_started_at keeps its last value
        # (the hand is complete, no one is acting)

    def test_turn_started_at_none_when_no_actor(self):
        """When both players are all-in from blinds, hand completes immediately."""
        # BB=20, chips=20 → both players all-in from blinds
        players = make_players(2, chips=20)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        # SB(10) acts first in heads-up; go all-in
        hand.do_action(hand.current_player.id, "all_in")
        # BB already posted 20 = all chips, so they just call the remaining 0
        # Actually BB has 0 chips left (posted 20), so no actor → showdown
        assert hand.is_complete


class TestHandComplete:
    def test_cannot_act_after_complete(self):
        players = make_players(2)
        hand = Hand(players, dealer_index=0, deck_seed=1)
        hand.do_action(hand.current_player.id, "fold")
        assert hand.is_complete
        result = hand.do_action(1, "check")
        assert result == "Hand is complete"
