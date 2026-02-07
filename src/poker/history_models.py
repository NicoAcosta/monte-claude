from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameEvent:
    game_id: int
    event_type: str
    timestamp: float
    hand_number: int
    data: str  # JSON-encoded payload
    sequence: int


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


@dataclass(frozen=True)
class PlayerStats:
    username: str
    games_played: int
    hands_played: int
    hands_won: int
    total_winnings: int  # net chips won across all games
    biggest_pot_won: int
