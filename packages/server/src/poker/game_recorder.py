from __future__ import annotations

import json
import time

from poker.history_models import GameEvent, HandSummary
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore


class GameRecorder:
    """Observer that receives game events and dispatches to persistent stores."""

    def __init__(
        self,
        game_id: int,
        event_store: GameEventStore,
        summary_store: HandSummaryStore,
        stats_store: PlayerStatsStore,
    ) -> None:
        self._game_id = game_id
        self._event_store = event_store
        self._summary_store = summary_store
        self._stats_store = stats_store
        self._sequence = 0
        self._current_hand_number = 0

    def on_event(self, event_type: str, data: dict) -> None:
        self._sequence += 1

        # Track current hand number from hand_started events
        if event_type == "hand_started":
            self._current_hand_number = data.get("hand_number", 0)

        hand_number = data.get("hand_number", self._current_hand_number)

        event = GameEvent(
            game_id=self._game_id,
            event_type=event_type,
            timestamp=time.time(),
            hand_number=hand_number,
            data=json.dumps(data),
            sequence=self._sequence,
        )
        self._event_store.append(event)

        if event_type == "hand_completed":
            self._materialize_hand_summary(data)
            self._update_player_stats(data)
        elif event_type == "game_started":
            player_names = data.get("player_names", [])
            self._stats_store.increment_games_played(player_names)

    def _materialize_hand_summary(self, data: dict) -> None:
        # Collect all winner IDs across all pots
        winner_ids: list[int] = []
        for _, ids in data.get("winners_by_pot", []):
            for wid in ids:
                if wid not in winner_ids:
                    winner_ids.append(wid)

        w_names: list[str] = data.get("winner_names", [])
        showdown_cards: dict[str, list[str]] = data.get("showdown_cards", {})

        # Filter showdown_cards to only winners
        winning_cards = {
            name: cards for name, cards in showdown_cards.items()
            if name in w_names
        }

        # Determine result type: if >1 non-folded player showed cards → showdown
        result_type = "showdown" if len(showdown_cards) > 1 else "fold"

        summary = HandSummary(
            game_id=self._game_id,
            hand_number=data.get("hand_number", 0),
            dealer_id=data.get("dealer_id", 0),
            player_ids=tuple(data.get("player_ids", [])),
            winner_ids=tuple(winner_ids),
            pot=data.get("pot", 0),
            community_cards=json.dumps(data.get("community_cards", [])),
            timestamp=time.time(),
            winner_names=tuple(w_names),
            winning_cards=json.dumps(winning_cards),
            result_type=result_type,
            token_symbol=data.get("token_symbol"),
        )
        self._summary_store.append(summary)

    def _update_player_stats(self, data: dict) -> None:
        player_names: list[str] = data.get("player_names", [])
        winner_names: list[str] = data.get("winner_names", [])
        pot: int = data.get("pot", 0)
        chip_deltas: dict[str, int] = data.get("chip_deltas", {})
        token_symbol: str = data.get("token_symbol") or "chips"

        if player_names:
            self._stats_store.update_from_hand(
                player_names=player_names,
                winner_names=winner_names,
                pot=pot,
                chip_deltas=chip_deltas,
                token_symbol=token_symbol,
            )
