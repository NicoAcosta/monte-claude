from __future__ import annotations

import json
import time
from collections.abc import Callable

from core.history_models import GameEvent
from core.history_store import GameEventStore, PlayerStatsStore

# Callback that receives (game_id, event_data) and writes game-type-specific
# summary records (e.g. poker hand summaries).
SummaryMaterializer = Callable[[int, dict], None]


class GameRecorder:
    """Observer that receives game events and dispatches to persistent stores."""

    def __init__(
        self,
        game_id: int,
        event_store: GameEventStore,
        stats_store: PlayerStatsStore,
        summary_materializer: SummaryMaterializer | None = None,
    ) -> None:
        self._game_id = game_id
        self._event_store = event_store
        self._stats_store = stats_store
        self._summary_materializer = summary_materializer
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
            if self._summary_materializer is not None:
                self._summary_materializer(self._game_id, data)
            self._update_player_stats(data)
        elif event_type == "game_started":
            player_names = data.get("player_names", [])
            self._stats_store.increment_games_played(player_names)

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
