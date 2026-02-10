from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from poker.deck import Card, Deck
from poker.evaluator import HandRank, best_hand


@dataclass
class PlayerInHand:
    id: int
    name: str
    chips: int
    hole_cards: list[Card] = field(default_factory=list)
    current_bet: int = 0
    total_bet_this_hand: int = 0
    is_folded: bool = False
    is_all_in: bool = False

    @property
    def is_active(self) -> bool:
        return not self.is_folded and not self.is_all_in


@dataclass(frozen=True)
class SidePot:
    amount: int
    eligible_player_ids: tuple[int, ...]


@dataclass(frozen=True)
class ActionRecord:
    id: int
    timestamp: float
    player_name: str
    action: str
    amount: int | None = None
    comment: str | None = None
    reason: str | None = None


PHASES = ("preflop", "flop", "turn", "river", "showdown", "complete")


class Hand:
    def __init__(
        self,
        players: list[PlayerInHand],
        dealer_index: int,
        small_blind: int = 10,
        big_blind: int = 20,
        deck_seed_hex: str | None = None,
        starting_action_id: int = 1,
        event_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        if len(players) < 2:
            raise ValueError("Need at least 2 players")

        self.players = players
        self.dealer_index = dealer_index
        self.small_blind = small_blind
        self.big_blind = big_blind
        self._event_callback = event_callback
        self.deck = Deck(seed_hex=deck_seed_hex)
        self.community_cards: list[Card] = []
        self.phase = "preflop"
        self.pot = 0
        self.actions: list[ActionRecord] = []
        self._action_id_counter = starting_action_id
        self.current_bet = 0  # highest bet this round
        self.min_raise_size = big_blind  # minimum raise increment
        self.current_turn_index: int | None = None
        self.turn_started_at: float | None = None
        self.winners_by_pot: list[tuple[int, list[int]]] = []  # (amount, [player_ids])
        self._acted_this_round: set[int] = set()  # player indices who acted since last raise

        self._post_blinds()
        self._deal_hole_cards()
        self._start_betting_round()

    def _record_action(
        self,
        player_name: str,
        action: str,
        amount: int | None = None,
        comment: str | None = None,
        reason: str | None = None,
    ) -> None:
        record = ActionRecord(
            id=self._action_id_counter,
            timestamp=time.time(),
            player_name=player_name,
            action=action,
            amount=amount,
            comment=comment,
            reason=reason,
        )
        self._action_id_counter += 1
        self.actions.append(record)
        self._notify("action", {
            "player_name": player_name,
            "action": action,
            "amount": amount,
            "comment": comment,
            "reason": reason,
            "action_id": record.id,
        })

    def _notify(self, event_type: str, data: dict) -> None:
        if self._event_callback:
            self._event_callback(event_type, data)

    @property
    def active_players(self) -> list[PlayerInHand]:
        return [p for p in self.players if not p.is_folded]

    @property
    def players_who_can_act(self) -> list[PlayerInHand]:
        return [p for p in self.players if p.is_active]

    @property
    def current_player(self) -> PlayerInHand | None:
        if self.current_turn_index is None:
            return None
        return self.players[self.current_turn_index]

    @property
    def is_complete(self) -> bool:
        return self.phase in ("showdown", "complete")

    def _player_index(self, offset_from_dealer: int) -> int:
        return (self.dealer_index + offset_from_dealer) % len(self.players)

    def _sb_index(self) -> int:
        if len(self.players) == 2:
            return self.dealer_index
        return self._player_index(1)

    def _bb_index(self) -> int:
        if len(self.players) == 2:
            return self._player_index(1)
        return self._player_index(2)

    def _post_blinds(self) -> None:
        sb_player = self.players[self._sb_index()]
        bb_player = self.players[self._bb_index()]

        sb_amount = min(self.small_blind, sb_player.chips)
        self._place_bet(sb_player, sb_amount)
        self._record_action(sb_player.name, "small_blind", sb_amount)

        bb_amount = min(self.big_blind, bb_player.chips)
        self._place_bet(bb_player, bb_amount)
        self._record_action(bb_player.name, "big_blind", bb_amount)

        self.current_bet = bb_amount

    def _place_bet(self, player: PlayerInHand, amount: int) -> None:
        actual = min(amount, player.chips)
        player.chips -= actual
        player.current_bet += actual
        player.total_bet_this_hand += actual
        self.pot += actual
        if player.chips == 0:
            player.is_all_in = True

    def _deal_hole_cards(self) -> None:
        for p in self.players:
            p.hole_cards = self.deck.deal(2)
            self._notify("cards_dealt", {
                "player_id": p.id,
                "player_name": p.name,
                "cards": [str(c) for c in p.hole_cards],
            })

    def _start_betting_round(self) -> None:
        if self._should_skip_to_showdown():
            self._advance_to_showdown()
            return

        self._acted_this_round = set()

        if self.phase == "preflop":
            # Preflop: action starts left of BB
            if len(self.players) == 2:
                start = self.dealer_index  # SB acts first preflop in heads-up
            else:
                start = self._player_index(3)
        else:
            # Postflop: start left of dealer
            start = self._player_index(1)
            for p in self.players:
                p.current_bet = 0
            self.current_bet = 0
            self.min_raise_size = self.big_blind

        self.current_turn_index = self._find_next_actor(start)
        if self.current_turn_index is not None:
            self.turn_started_at = time.time()
        else:
            self.turn_started_at = None
            self._end_betting_round()

    def _should_skip_to_showdown(self) -> bool:
        active = self.active_players
        if len(active) <= 1:
            return True
        can_act = self.players_who_can_act
        return len(can_act) == 0

    def _advance_to_showdown(self) -> None:
        # Deal remaining community cards
        while len(self.community_cards) < 5:
            if len(self.community_cards) == 0:
                cards = self.deck.deal(3)
                self.community_cards.extend(cards)
                self._notify("community_dealt", {
                    "cards": [str(c) for c in cards],
                    "phase": "flop",
                })
            else:
                cards = self.deck.deal(1)
                phase = "turn" if len(self.community_cards) == 3 else "river"
                self.community_cards.extend(cards)
                self._notify("community_dealt", {
                    "cards": [str(c) for c in cards],
                    "phase": phase,
                })

        active = self.active_players
        if len(active) == 1:
            # Everyone else folded
            winner = active[0]
            winner.chips += self.pot
            self.winners_by_pot = [(self.pot, [winner.id])]
            self.phase = "complete"
        else:
            self.phase = "showdown"
            self._resolve_showdown()

    def _find_next_actor(self, start_index: int) -> int | None:
        n = len(self.players)
        for i in range(n):
            idx = (start_index + i) % n
            p = self.players[idx]
            if p.is_active:
                return idx
        return None

    def _advance_turn(self) -> None:
        assert self.current_turn_index is not None

        # Check if all active players have acted since the last raise
        active_indices = {
            i for i, p in enumerate(self.players) if p.is_active
        }
        if active_indices and active_indices.issubset(self._acted_this_round):
            self._end_betting_round()
            return

        next_idx = self._find_next_actor(
            (self.current_turn_index + 1) % len(self.players)
        )

        if next_idx is None:
            self._end_betting_round()
            return

        self.current_turn_index = next_idx
        self.turn_started_at = time.time()

    def _end_betting_round(self) -> None:
        self.current_turn_index = None

        active = self.active_players
        if len(active) <= 1:
            self._advance_to_showdown()
            return

        if self.phase == "preflop":
            cards = self.deck.deal(3)
            self.community_cards.extend(cards)
            self.phase = "flop"
            self._notify("community_dealt", {
                "cards": [str(c) for c in cards],
                "phase": "flop",
            })
        elif self.phase == "flop":
            cards = self.deck.deal(1)
            self.community_cards.extend(cards)
            self.phase = "turn"
            self._notify("community_dealt", {
                "cards": [str(c) for c in cards],
                "phase": "turn",
            })
        elif self.phase == "turn":
            cards = self.deck.deal(1)
            self.community_cards.extend(cards)
            self.phase = "river"
            self._notify("community_dealt", {
                "cards": [str(c) for c in cards],
                "phase": "river",
            })
        elif self.phase == "river":
            self.phase = "showdown"
            self._resolve_showdown()
            return

        self._start_betting_round()

    def do_action(
        self,
        player_id: int,
        action: str,
        amount: int | None = None,
        comment: str | None = None,
        reason: str | None = None,
    ) -> str:
        if self.is_complete:
            return "Hand is complete"

        player = self._get_player(player_id)
        if player is None:
            return "Player not found"

        if self.current_player is None or self.current_player.id != player_id:
            return "Not your turn"

        if action == "fold":
            return self._do_fold(player, comment, reason)
        elif action == "check":
            return self._do_check(player, comment, reason)
        elif action == "call":
            return self._do_call(player, comment, reason)
        elif action == "bet":
            return self._do_bet(player, amount, comment, reason)
        elif action == "raise":
            return self._do_raise(player, amount, comment, reason)
        elif action == "all_in":
            return self._do_all_in(player, comment, reason)
        else:
            return f"Unknown action: {action}"

    def _get_player(self, player_id: int) -> PlayerInHand | None:
        for p in self.players:
            if p.id == player_id:
                return p
        return None

    def _mark_acted(self, player_index: int) -> None:
        self._acted_this_round.add(player_index)

    def _reset_acted_for_raise(self, raiser_index: int) -> None:
        """When someone raises, everyone else needs to act again."""
        self._acted_this_round = {raiser_index}

    def _do_fold(self, player: PlayerInHand, comment: str | None = None, reason: str | None = None) -> str:
        player.is_folded = True
        self._mark_acted(self.current_turn_index)
        self._record_action(player.name, "fold", comment=comment, reason=reason)

        active = self.active_players
        if len(active) == 1:
            winner = active[0]
            winner.chips += self.pot
            self.winners_by_pot = [(self.pot, [winner.id])]
            self.phase = "complete"
            self.current_turn_index = None
            return "ok"

        self._advance_turn()
        return "ok"

    def _do_check(self, player: PlayerInHand, comment: str | None = None, reason: str | None = None) -> str:
        if player.current_bet < self.current_bet:
            return "Cannot check, there is a bet to match"

        self._mark_acted(self.current_turn_index)
        self._record_action(player.name, "check", comment=comment, reason=reason)
        self._advance_turn()
        return "ok"

    def _do_call(self, player: PlayerInHand, comment: str | None = None, reason: str | None = None) -> str:
        to_call = self.current_bet - player.current_bet
        if to_call <= 0:
            return "Nothing to call, use check"

        actual = min(to_call, player.chips)
        self._place_bet(player, actual)
        self._mark_acted(self.current_turn_index)
        self._record_action(player.name, "call", player.current_bet, comment=comment, reason=reason)
        self._advance_turn()
        return "ok"

    def _do_bet(self, player: PlayerInHand, amount: int | None, comment: str | None = None, reason: str | None = None) -> str:
        if self.current_bet > 0:
            return "Cannot bet, someone already bet. Use raise."

        if amount is None:
            return "Bet requires an amount"

        if amount < self.big_blind and amount < player.chips:
            return f"Minimum bet is {self.big_blind}"

        if amount > player.chips:
            return f"Not enough chips. You have {player.chips}"

        self._place_bet(player, amount)
        self.current_bet = player.current_bet
        self.min_raise_size = amount
        self._reset_acted_for_raise(self.current_turn_index)
        self._record_action(player.name, "bet", player.current_bet, comment=comment, reason=reason)
        self._advance_turn()
        return "ok"

    def _do_raise(self, player: PlayerInHand, amount: int | None, comment: str | None = None, reason: str | None = None) -> str:
        if self.current_bet == 0:
            return "No bet to raise. Use bet."

        if amount is None:
            return "Raise requires an amount (total bet)"

        additional = amount - player.current_bet
        if additional <= 0:
            return f"Raise amount must be more than your current bet of {player.current_bet}"

        raise_increment = amount - self.current_bet
        if raise_increment < self.min_raise_size and additional < player.chips:
            return f"Minimum raise is {self.current_bet + self.min_raise_size}"

        if additional > player.chips:
            return f"Not enough chips. You have {player.chips}. Use all_in."

        self._place_bet(player, additional)
        self.min_raise_size = max(self.min_raise_size, raise_increment)
        self.current_bet = player.current_bet
        self._reset_acted_for_raise(self.current_turn_index)
        self._record_action(player.name, "raise", player.current_bet, comment=comment, reason=reason)
        self._advance_turn()
        return "ok"

    def _do_all_in(self, player: PlayerInHand, comment: str | None = None, reason: str | None = None) -> str:
        amount = player.chips
        self._place_bet(player, amount)

        if player.current_bet > self.current_bet:
            raise_increment = player.current_bet - self.current_bet
            self.min_raise_size = max(self.min_raise_size, raise_increment)
            self.current_bet = player.current_bet
            self._reset_acted_for_raise(self.current_turn_index)
        else:
            self._mark_acted(self.current_turn_index)

        self._record_action(player.name, "all_in", player.current_bet, comment=comment, reason=reason)
        self._advance_turn()
        return "ok"

    def _resolve_showdown(self) -> None:
        active = self.active_players
        side_pots = self._calculate_side_pots()
        self.winners_by_pot = []

        for pot_amount, eligible_ids in side_pots:
            eligible = [p for p in active if p.id in eligible_ids]
            if not eligible:
                continue

            hand_ranks: list[tuple[PlayerInHand, HandRank]] = []
            for p in eligible:
                hr = best_hand(p.hole_cards + self.community_cards)
                hand_ranks.append((p, hr))

            best_rank = max(hr for _, hr in hand_ranks)
            winners = [p for p, hr in hand_ranks if hr == best_rank]

            share = pot_amount // len(winners)
            remainder = pot_amount % len(winners)

            for i, w in enumerate(winners):
                award = share + (1 if i < remainder else 0)
                w.chips += award

            self.winners_by_pot.append((pot_amount, [w.id for w in winners]))

        self.phase = "complete"
        self.current_turn_index = None

    def _calculate_side_pots(self) -> list[tuple[int, set[int]]]:
        """Calculate side pots based on all-in amounts."""
        active = self.active_players
        if not active:
            return []

        # Collect total bets from non-folded players
        contributions: list[tuple[int, int]] = []  # (total_bet, player_id)
        for p in self.players:
            if not p.is_folded and p.total_bet_this_hand > 0:
                contributions.append((p.total_bet_this_hand, p.id))

        if not contributions:
            return [(self.pot, {p.id for p in active})]

        # Sort by total bet amount
        contributions.sort(key=lambda x: x[0])

        pots: list[tuple[int, set[int]]] = []
        prev_level = 0

        # Also include folded players' contributions
        all_bets = [(p.total_bet_this_hand, p.id) for p in self.players if p.total_bet_this_hand > 0]

        for bet_level, _ in contributions:
            if bet_level <= prev_level:
                continue

            eligible_ids = set()
            pot_amount = 0

            for player_bet, pid in all_bets:
                contribution = min(player_bet, bet_level) - min(player_bet, prev_level)
                if contribution > 0:
                    pot_amount += contribution
                # Only non-folded players are eligible to win
                player = self._get_player(pid)
                if player and not player.is_folded and player_bet >= bet_level:
                    eligible_ids.add(pid)

            if pot_amount > 0 and eligible_ids:
                pots.append((pot_amount, eligible_ids))

            prev_level = bet_level

        return pots

    def get_amount_to_call(self, player_id: int) -> int:
        player = self._get_player(player_id)
        if player is None:
            return 0
        return min(self.current_bet - player.current_bet, player.chips)

    def get_min_raise(self) -> int:
        return self.current_bet + self.min_raise_size

    def get_side_pots_info(self) -> list[SidePot]:
        side_pots = self._calculate_side_pots()
        if len(side_pots) <= 1:
            return []
        return [
            SidePot(amount=amount, eligible_player_ids=tuple(sorted(ids)))
            for amount, ids in side_pots
        ]
