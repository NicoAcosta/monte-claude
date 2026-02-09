"""Game configuration — payment, escrow, and capacity settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GameConfig:
    mode: str                                          # "offchain" | "onchain"
    buy_in: int = 0
    max_players: int = 0
    token: str | None = None
    funded: bool = False
    escrow_salt: bytes | None = None
    escrow_address: str | None = None
    escrow_config: Any | None = None
    offchain_settlement: list[tuple[str, int]] | None = None

    def is_at_capacity(self, player_count: int) -> bool:
        return self.max_players > 0 and player_count >= self.max_players
