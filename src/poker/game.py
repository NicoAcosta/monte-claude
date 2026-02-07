from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from poker.hand import ActionRecord, Hand, PlayerInHand

STARTING_CHIPS = 1000
SMALL_BLIND = 10
BIG_BLIND = 20


@dataclass
class RegisteredPlayer:
    id: int
    name: str
    chips: int = STARTING_CHIPS


class Game:
    def __init__(
        self,
        event_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._players: list[RegisteredPlayer] = []
        self._next_id = 1
        self._next_action_id = 1
        self.started = False
        self.hand_number = 0
        self.dealer_index = 0
        self.current_hand: Hand | None = None
        self.previous_hand: Hand | None = None
        self.game_over = False
        self.winner: str | None = None
        self.recent_actions: list[ActionRecord] = []
        self.commentary_text: str | None = None
        self._event_callback = event_callback

    def _notify(self, event_type: str, data: dict) -> None:
        if self._event_callback:
            self._event_callback(event_type, data)

    @property
    def player_count(self) -> int:
        return len(self._players)

    @property
    def alive_players(self) -> list[RegisteredPlayer]:
        return [p for p in self._players if p.chips > 0]

    def register(self, name: str) -> RegisteredPlayer:
        if self.started:
            raise ValueError("Game already started")
        if not name.strip():
            raise ValueError("Name cannot be empty")
        for p in self._players:
            if p.name == name:
                raise ValueError(f"Name '{name}' already taken")

        player = RegisteredPlayer(id=self._next_id, name=name)
        self._next_id += 1
        self._players.append(player)
        return player

    def get_player(self, player_id: int) -> RegisteredPlayer | None:
        for p in self._players:
            if p.id == player_id:
                return p
        return None

    def get_player_by_name(self, name: str) -> RegisteredPlayer | None:
        for p in self._players:
            if p.name == name:
                return p
        return None

    def start(self) -> int:
        if self.started:
            raise ValueError("Game already started")
        if len(self._players) < 2:
            raise ValueError("Need at least 2 players")

        self.started = True
        self._start_new_hand()
        return self.hand_number

    def do_action(
        self, player_id: int, action: str, amount: int | None = None, comment: str | None = None,
    ) -> str:
        if not self.started:
            return "Game not started"
        if self.game_over:
            return "Game is over"
        if self.current_hand is None:
            return "No active hand"

        result = self.current_hand.do_action(player_id, action, amount, comment=comment)

        if result == "ok" and self.current_hand.is_complete:
            self._finish_hand()

        return result

    def _start_new_hand(self) -> None:
        alive = self.alive_players
        if len(alive) < 2:
            self.game_over = True
            if alive:
                self.winner = alive[0].name
            return

        self.hand_number += 1

        # Build hand players from alive registered players
        hand_players = [
            PlayerInHand(id=p.id, name=p.name, chips=p.chips)
            for p in alive
        ]

        # Wrap dealer_index
        self.dealer_index = self.dealer_index % len(hand_players)

        # Emit hand_started BEFORE Hand construction (Hand.__init__ posts blinds + deals)
        self._notify("hand_started", {
            "hand_number": self.hand_number,
            "dealer_id": hand_players[self.dealer_index].id,
            "players": [
                {"id": p.id, "name": p.name, "chips": p.chips}
                for p in hand_players
            ],
            "small_blind": SMALL_BLIND,
            "big_blind": BIG_BLIND,
        })

        self.current_hand = Hand(
            players=hand_players,
            dealer_index=self.dealer_index,
            small_blind=SMALL_BLIND,
            big_blind=BIG_BLIND,
            starting_action_id=self._next_action_id,
            event_callback=self._event_callback,
        )

        self.recent_actions = []

        # If hand is already complete (e.g., only one player can act after blinds)
        if self.current_hand.is_complete:
            self._finish_hand()

    def _finish_hand(self) -> None:
        if self.current_hand is None:
            return

        hand = self.current_hand

        # Store completed hand for spectator delay
        self.previous_hand = hand
        self._next_action_id = hand._action_id_counter

        # Copy recent actions
        self.recent_actions = list(hand.actions)

        # Compute chip deltas before updating registered player chips
        chips_before: dict[str, int] = {}
        for rp in self._players:
            chips_before[rp.name] = rp.chips

        # Update registered player chips from hand results
        for hp in hand.players:
            rp = self.get_player(hp.id)
            if rp is not None:
                rp.chips = hp.chips

        chip_deltas = {
            rp.name: rp.chips - chips_before[rp.name]
            for rp in self._players
            if rp.name in chips_before
        }

        # Collect winner info
        all_winner_ids: list[int] = []
        for _, ids in hand.winners_by_pot:
            for wid in ids:
                if wid not in all_winner_ids:
                    all_winner_ids.append(wid)
        winner_names = [
            hp.name for hp in hand.players if hp.id in all_winner_ids
        ]

        # Emit hand_completed event
        self._notify("hand_completed", {
            "hand_number": self.hand_number,
            "dealer_id": hand.players[hand.dealer_index].id,
            "player_ids": [p.id for p in hand.players],
            "player_names": [p.name for p in hand.players],
            "winner_ids": all_winner_ids,
            "winner_names": winner_names,
            "winners_by_pot": list(hand.winners_by_pot),
            "pot": hand.pot,
            "community_cards": [str(c) for c in hand.community_cards],
            "chip_deltas": chip_deltas,
            "showdown_cards": {
                p.name: [str(c) for c in p.hole_cards]
                for p in hand.players if not p.is_folded
            },
        })

        # Eliminate busted players (chips == 0 means they're out)
        eliminated = [rp for rp in self._players if rp.chips == 0]
        for rp in eliminated:
            self._notify("player_eliminated", {
                "hand_number": self.hand_number,
                "player_name": rp.name,
                "player_id": rp.id,
            })

        alive = self.alive_players
        if len(alive) <= 1:
            self.game_over = True
            if alive:
                self.winner = alive[0].name
            self._notify("game_over", {
                "hand_number": self.hand_number,
                "winner_name": self.winner,
            })
            self.current_hand = None
            return

        # Rotate dealer
        self.dealer_index = (self.dealer_index + 1) % len(alive)

        # Start next hand
        self._start_new_hand()

    def get_sb_player_id(self) -> int:
        if self.current_hand is None:
            return 0
        return self.current_hand.players[self.current_hand._sb_index()].id

    def get_bb_player_id(self) -> int:
        if self.current_hand is None:
            return 0
        return self.current_hand.players[self.current_hand._bb_index()].id

    def get_dealer_player_id(self) -> int:
        if self.current_hand is None:
            return 0
        return self.current_hand.players[self.current_hand.dealer_index].id
