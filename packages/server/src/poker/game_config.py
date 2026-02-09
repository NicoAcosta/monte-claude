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
    token_decimals: int = 0
    token_symbol: str | None = None
    funded: bool = False
    escrow_salt: bytes | None = None
    escrow_address: str | None = None
    escrow_config: Any | None = None
    offchain_settlement: list[tuple[str, int]] | None = None

    def is_at_capacity(self, player_count: int) -> bool:
        return self.max_players > 0 and player_count >= self.max_players

    @property
    def buy_in_display(self) -> str:
        """Human-readable buy-in (e.g., '1000 MONTE' or '500 credits')."""
        if self.buy_in == 0:
            return "Free"
        if self.token_decimals > 0:
            raw = self.buy_in / (10 ** self.token_decimals)
            amount = f"{raw:g}"
        else:
            amount = str(self.buy_in)
        symbol = self.token_symbol or ("credits" if self.mode == "offchain" else None)
        if symbol:
            return f"{amount} {symbol}"
        return amount
