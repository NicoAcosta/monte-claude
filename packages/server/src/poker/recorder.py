"""Poker-specific summary materializer for GameRecorder."""

from __future__ import annotations

import json
from collections.abc import Callable

from poker.history_models import HandSummary
from poker.history_store import HandSummaryStore


def make_poker_materializer(summary_store: HandSummaryStore) -> Callable[[int, dict], None]:
    """Return a callback that writes poker hand summaries from hand_completed events."""

    def _materialize(game_id: int, data: dict) -> None:
        summary = HandSummary(
            game_id=game_id,
            hand_number=data.get("hand_number", 0),
            dealer_id=data.get("dealer_id", 0),
            player_ids=tuple(data.get("player_ids", [])),
            winner_ids=tuple(data.get("winner_ids", [])),
            pot=data.get("pot", 0),
            community_cards=data.get("community_cards", ""),
            timestamp=data.get("timestamp", 0.0),
            winner_names=tuple(data.get("winner_names", [])),
            winning_cards=json.dumps(data.get("winning_cards", {})),
            result_type=data.get("result_type", "fold"),
            token_symbol=data.get("token_symbol"),
        )
        summary_store.append(summary)

    return _materialize
