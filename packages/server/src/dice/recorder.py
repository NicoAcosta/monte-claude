"""Dice summary materializer — writes round summaries to round_summaries table."""

from __future__ import annotations

import time
from collections.abc import Callable

from core.round_summary_store import RoundSummary, RoundSummaryStore


def make_dice_materializer(
    summary_store: RoundSummaryStore,
) -> Callable[[int, dict], None]:
    """Return a materializer callback for the GameRecorder.

    Called on each "hand_completed" event with the event data dict.
    """
    def _materialize(game_id: int, data: dict) -> None:
        summary = RoundSummary(
            game_id=game_id,
            game_type="dice",
            round_number=data["hand_number"],
            player_ids=tuple(int(k) for k in data.get("bets", {}).keys()),
            winner_ids=tuple(data.get("winner_ids", [])),
            pot=data.get("pot", 0),
            details={
                "dice": data.get("dice"),
                "total": data.get("total"),
                "category": data.get("category"),
                "bets": data.get("bets", {}),
                "payouts": data.get("payouts", {}),
            },
            timestamp=time.time(),
            seed_hex=data.get("seed_hex", ""),
            seed_commitment=data.get("seed_commitment", ""),
        )
        summary_store.append(summary)

    return _materialize
