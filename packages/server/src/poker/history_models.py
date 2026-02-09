from __future__ import annotations

from dataclasses import dataclass

# Re-export from core for backward compatibility
from core.history_models import GameEvent, PlayerStats  # noqa: F401


@dataclass(frozen=True)
class HandSummary:
    game_id: int
    hand_number: int
    dealer_id: int
    player_ids: tuple[int, ...]
    winner_ids: tuple[int, ...]
    pot: int
    community_cards: str  # JSON list of card strings
    timestamp: float
    winner_names: tuple[str, ...] = ()
    winning_cards: str = "{}"  # JSON: {name: [cards]}
    result_type: str = "fold"  # "fold" or "showdown"
    token_symbol: str | None = None
