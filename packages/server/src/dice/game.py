"""Dice (Over/Under) game — implements GameProtocol."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from core.game_protocol import (
    STARTING_CHIPS,
    ACTION_TIMEOUT,
    EXTENSIONS_PER_PLAYER,
    RegisteredPlayer,
)
from dice.round import resolve_round, RoundResult

_log = logging.getLogger("dice.game")

ANTE = 20
VALID_BETS = frozenset({"high", "low", "seven"})


class DiceGame:
    def __init__(
        self,
        event_callback: Callable[[str, dict], None] | None = None,
        action_timeout: float = ACTION_TIMEOUT,
        extensions_per_player: int = EXTENSIONS_PER_PLAYER,
        first_hand_grace: float = 120.0,
        ante: int = ANTE,
    ) -> None:
        self._players: list[RegisteredPlayer] = []
        self._next_id = 1
        self.started = False
        self.started_at: float | None = None
        self.hand_number = 0  # "round number" — kept as hand_number for protocol compat
        self.game_over = False
        self.winner: str | None = None
        self._event_callback = event_callback
        self._ante = ante

        # Current round state
        self._phase: str = "waiting"  # waiting | betting | reveal | complete
        self._bets: dict[int, str] = {}  # player_id → bet
        self._round_players: list[RegisteredPlayer] = []  # players who anted this round
        self._current_turn_index: int | None = None
        self._turn_started_at: float | None = None
        self._last_result: RoundResult | None = None

        # Chat
        self._chat_log: list[tuple[str, str, float]] = []
        self._chat_max: int = 100

        # Timer
        self.action_timeout = action_timeout
        self.extensions_per_player = extensions_per_player
        self._time_extensions: dict[int, int] = {}
        self._extra_time: float = 0.0
        self.first_hand_grace = first_hand_grace
        self._state_version: int = 0

    # ── Notify ────────────────────────────────────────────

    def _notify(self, event_type: str, data: dict) -> None:
        if self._event_callback:
            self._event_callback(event_type, data)

    # ── Chat ──────────────────────────────────────────────

    def add_chat(self, player_name: str, message: str) -> None:
        self._chat_log.append((player_name, message, time.time()))
        if len(self._chat_log) > self._chat_max:
            self._chat_log = self._chat_log[-self._chat_max:]
        self._notify("chat", {"player_name": player_name, "message": message})

    @property
    def chat_log(self) -> list[tuple[str, str, float]]:
        return list(self._chat_log)

    # ── Timer ─────────────────────────────────────────────

    @property
    def turn_deadline(self) -> float | None:
        if self._turn_started_at is None or self._current_turn_index is None:
            return None
        return self._turn_started_at + self.action_timeout + self._extra_time

    def _check_timeout(self) -> str | None:
        if self.action_timeout <= 0:
            return None
        if self._current_turn_index is None:
            return None
        deadline = self.turn_deadline
        if deadline is None or time.time() <= deadline:
            return None
        player = self._betting_order[self._current_turn_index]
        player_name = player.name
        # Auto-pick "high" as default timeout action
        self.do_action(player.id, "high", comment="[timeout]")
        self._notify("timeout_action", {"player_name": player_name, "action": "high"})
        return player_name

    def use_extension(self, player_id: int) -> tuple[float, int] | None:
        if self._current_turn_index is None:
            return None
        current = self._betting_order[self._current_turn_index]
        if current.id != player_id:
            return None
        remaining = self._time_extensions.get(player_id, 0)
        if remaining <= 0:
            return None
        self._time_extensions[player_id] = remaining - 1
        self._extra_time += self.action_timeout
        new_deadline = self.turn_deadline
        assert new_deadline is not None
        self._notify("time_extension", {
            "player_id": player_id,
            "new_deadline": new_deadline,
            "extensions_remaining": remaining - 1,
        })
        return (new_deadline, remaining - 1)

    def get_extensions_remaining(self, player_id: int) -> int:
        return self._time_extensions.get(player_id, 0)

    # ── Properties (GameProtocol) ─────────────────────────

    @property
    def state_version(self) -> int:
        return self._state_version

    @property
    def player_count(self) -> int:
        return len(self._players)

    @property
    def alive_players(self) -> list[RegisteredPlayer]:
        return [p for p in self._players if p.chips > 0 and not p.resigned]

    @property
    def players(self) -> list[RegisteredPlayer]:
        return list(self._players)

    @property
    def game_type(self) -> str:
        return "dice"

    @property
    def starting_chips(self) -> int:
        return STARTING_CHIPS

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def ante(self) -> int:
        return self._ante

    @property
    def current_player(self) -> RegisteredPlayer | None:
        if self._current_turn_index is None:
            return None
        order = self._betting_order
        if self._current_turn_index >= len(order):
            return None
        return order[self._current_turn_index]

    @property
    def last_result(self) -> RoundResult | None:
        return self._last_result

    @property
    def bets(self) -> dict[int, str]:
        return dict(self._bets)

    @property
    def _betting_order(self) -> list[RegisteredPlayer]:
        """Players who anted and haven't resigned — the active round participants."""
        return [p for p in self._round_players if not p.resigned]

    # ── Registration ──────────────────────────────────────

    def register(self, name: str, wallet_address: str | None = None) -> RegisteredPlayer:
        if self.started:
            raise ValueError("Game already started")
        if not name.strip():
            raise ValueError("Name cannot be empty")
        for p in self._players:
            if p.name == name:
                raise ValueError(f"Name '{name}' already taken")
        player = RegisteredPlayer(id=self._next_id, name=name, wallet_address=wallet_address)
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

    # ── Game lifecycle ────────────────────────────────────

    def start(self) -> int:
        if self.started:
            raise ValueError("Game already started")
        if len(self._players) < 2:
            raise ValueError("Need at least 2 players")
        self.started = True
        self.started_at = time.time()
        for p in self._players:
            self._time_extensions[p.id] = self.extensions_per_player
        self._start_new_round()
        self._extra_time = self.first_hand_grace
        _log.info("game_started players=%d", len(self._players))
        return self.hand_number

    def _start_new_round(self) -> None:
        alive = self.alive_players
        if len(alive) < 2:
            self.game_over = True
            if alive:
                self.winner = alive[0].name
            self._notify("game_over", {
                "hand_number": self.hand_number,
                "winner_name": self.winner,
            })
            return

        # Check all alive players can afford the ante
        can_play = [p for p in alive if p.chips >= self._ante]
        if len(can_play) < 2:
            # Not enough players can ante — game over, richest wins
            self.game_over = True
            richest = max(alive, key=lambda p: p.chips)
            self.winner = richest.name
            self._notify("game_over", {
                "hand_number": self.hand_number,
                "winner_name": self.winner,
            })
            return

        self.hand_number += 1
        self._phase = "betting"
        self._bets.clear()
        # Don't clear _last_result — keep it visible for spectators until next round resolves

        # Auto-ante: deduct from all players who can afford it
        self._round_players = list(can_play)
        for p in can_play:
            p.chips -= self._ante

        self._current_turn_index = 0
        self._turn_started_at = time.time()
        self._extra_time = 0.0

        self._notify("hand_started", {
            "hand_number": self.hand_number,
            "ante": self._ante,
            "player_count": len(can_play),
        })

    def do_action(
        self,
        player_id: int,
        action: str,
        amount: int | None = None,
        comment: str | None = None,
        reason: str | None = None,
    ) -> str:
        if not self.started:
            return "Game not started"
        if self.game_over:
            return "Game is over"
        if self._phase != "betting":
            return "Not in betting phase"
        if self._current_turn_index is None:
            return "No active turn"

        order = self._betting_order
        if self._current_turn_index >= len(order):
            return "Round betting complete"

        current = order[self._current_turn_index]
        if current.id != player_id:
            return "Not your turn"

        action = action.lower().strip()
        if action not in VALID_BETS:
            return f"Invalid bet. Choose: high, low, or seven"

        self._bets[player_id] = action
        self._state_version += 1
        self._extra_time = 0.0

        self._notify("action", {
            "hand_number": self.hand_number,
            "player_id": player_id,
            "player_name": current.name,
            "action": action,
            "comment": comment,
        })

        # Advance to next player
        self._current_turn_index += 1
        if self._current_turn_index >= len(order):
            # All bets placed — resolve
            self._resolve_round()
        else:
            self._turn_started_at = time.time()

        return "ok"

    def _resolve_round(self) -> None:
        self._phase = "reveal"
        self._current_turn_index = None
        self._turn_started_at = None

        result = resolve_round(self._bets, self._ante)
        self._last_result = result

        # Apply payouts
        for pid, payout in result.payouts.items():
            p = self.get_player(pid)
            if p is not None:
                p.chips += payout

        self._state_version += 1

        self._notify("round_resolved", {
            "hand_number": self.hand_number,
            "dice": list(result.dice),
            "total": result.total,
            "category": result.category,
            "winner_ids": list(result.winner_ids),
            "pot": result.pot,
            "payouts": result.payouts,
        })

        self._notify("hand_completed", {
            "hand_number": self.hand_number,
            "dice": list(result.dice),
            "total": result.total,
            "category": result.category,
            "winner_ids": list(result.winner_ids),
            "pot": result.pot,
            "payouts": result.payouts,
            "bets": {str(pid): bet for pid, bet in self._bets.items()},
            "player_chips": {
                str(p.id): p.chips for p in self._players
            },
        })

        self._phase = "complete"

        # Auto-start next round
        self._start_new_round()

    def resign(self, player_id: int) -> str:
        if not self.started:
            return "Game not started"
        if self.game_over:
            return "Game is over"

        player = self.get_player(player_id)
        if player is None:
            return "Player not found"
        if player.resigned:
            return "Already resigned"
        if player.chips <= 0:
            return "Already eliminated"

        player.resigned = True
        self._state_version += 1

        _log.info("player_resigned player=%s player_id=%d", player.name, player.id)
        self._notify("player_resigned", {
            "player_name": player.name,
            "player_id": player.id,
        })

        # If it was their turn, skip to next
        if self._current_turn_index is not None and self._phase == "betting":
            order = self._betting_order
            # Recalculate: the order changed because this player is now resigned
            if self._current_turn_index >= len(order):
                # Was the last player — resolve
                if self._bets:
                    self._resolve_round()
                else:
                    self._start_new_round()
            else:
                self._turn_started_at = time.time()
                self._extra_time = 0.0

        # Check game over
        alive = self.alive_players
        if len(alive) <= 1 and not self.game_over:
            self.game_over = True
            if alive:
                self.winner = alive[0].name
            self._notify("game_over", {
                "hand_number": self.hand_number,
                "winner_name": self.winner,
            })

        return "ok"
