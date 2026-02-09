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
class PlayerStats:
    username: str
    games_played: int
    hands_played: int
    hands_won: int
    total_winnings: int  # net chips won across all games
    biggest_pot_won: int
