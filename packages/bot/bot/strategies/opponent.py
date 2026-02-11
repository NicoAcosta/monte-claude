"""Opponent modeling: track betting patterns to classify opponents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OpponentProfile:
    """Running stats for a single opponent across hands."""

    hands_seen: int = 0
    vpip_count: int = 0  # voluntarily put $ in pot (not just blinds)
    pfr_count: int = 0   # preflop raise count
    aggression_bets: int = 0  # bets + raises postflop
    aggression_calls: int = 0  # calls postflop
    aggression_checks: int = 0  # checks postflop
    fold_to_raise: int = 0
    raise_faced: int = 0
    went_to_showdown: int = 0  # approximate: saw river without folding
    all_in_count: int = 0

    @property
    def vpip(self) -> float:
        """Voluntarily put $ in pot percentage."""
        return self.vpip_count / max(self.hands_seen, 1)

    @property
    def pfr(self) -> float:
        """Preflop raise frequency."""
        return self.pfr_count / max(self.hands_seen, 1)

    @property
    def aggression_factor(self) -> float:
        """AF = (bets + raises) / calls. Higher = more aggressive."""
        return self.aggression_bets / max(self.aggression_calls, 1)

    @property
    def fold_to_raise_pct(self) -> float:
        return self.fold_to_raise / max(self.raise_faced, 1)

    @property
    def is_passive(self) -> bool:
        return self.aggression_factor < 1.0 and self.hands_seen >= 5

    @property
    def is_aggressive(self) -> bool:
        return self.aggression_factor > 2.0 and self.hands_seen >= 5

    @property
    def is_tight(self) -> bool:
        return self.vpip < 0.30 and self.hands_seen >= 8

    @property
    def is_loose(self) -> bool:
        return self.vpip > 0.55 and self.hands_seen >= 8


class OpponentTracker:
    """Tracks opponent stats across hands from game state observations."""

    def __init__(self) -> None:
        self._profiles: dict[str, OpponentProfile] = {}
        self._last_hand: int = -1
        self._hand_participants: set[str] = set()
        self._seen_actions: set[tuple[int, str, str]] = set()

    def profile(self, name: str) -> OpponentProfile:
        if name not in self._profiles:
            self._profiles[name] = OpponentProfile()
        return self._profiles[name]

    def update(self, state: dict[str, Any]) -> None:
        """Update profiles from game state. Call on every poll."""
        hand = state.get("hand_number", 0)
        phase = state.get("phase", "")

        # New hand — mark participation
        if hand != self._last_hand:
            # Record previous hand's participants
            for name in self._hand_participants:
                self.profile(name).hands_seen += 1
            self._hand_participants = set()
            self._seen_actions = set()
            self._last_hand = hand

        # Track all non-folded players as participants
        for p in state.get("players", []):
            if not p.get("is_folded", False) and not p.get("is_resigned", False):
                self._hand_participants.add(p["name"])

        # Analyze recent actions
        for action_entry in state.get("recent_actions", []):
            player_name = action_entry.get("player", "")
            action = action_entry.get("action", "")
            amount = action_entry.get("amount", 0)
            key = (hand, player_name, f"{action}_{amount}")

            if key in self._seen_actions:
                continue
            self._seen_actions.add(key)

            prof = self.profile(player_name)
            self._hand_participants.add(player_name)

            if phase == "preflop":
                if action in ("raise", "bet", "all_in"):
                    prof.pfr_count += 1
                    prof.vpip_count += 1
                elif action == "call":
                    prof.vpip_count += 1
            else:
                # Postflop
                if action in ("bet", "raise"):
                    prof.aggression_bets += 1
                elif action == "call":
                    prof.aggression_calls += 1
                elif action == "check":
                    prof.aggression_checks += 1

            if action == "all_in":
                prof.all_in_count += 1
                prof.aggression_bets += 1

            if action == "fold":
                prof.fold_to_raise += 1
                prof.raise_faced += 1
            elif action == "call" and phase != "preflop":
                prof.raise_faced += 1  # approximate: called facing action
