"""Game protocol — shared interface and types for all game implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

STARTING_CHIPS = 1000
ACTION_TIMEOUT = 30.0
EXTENSIONS_PER_PLAYER = 3


@dataclass
class RegisteredPlayer:
    id: int
    name: str
    chips: int = STARTING_CHIPS
    wallet_address: str | None = None
    resigned: bool = False


@runtime_checkable
class GameProtocol(Protocol):
    started: bool
    started_at: float | None
    game_over: bool
    winner: str | None
    hand_number: int  # "round_number" for dice; kept as hand_number for DB compat
    action_timeout: float
    state_version: int

    @property
    def game_type(self) -> str: ...
    @property
    def starting_chips(self) -> int: ...
    @property
    def player_count(self) -> int: ...
    @property
    def alive_players(self) -> list[RegisteredPlayer]: ...
    @property
    def players(self) -> list[RegisteredPlayer]: ...
    @property
    def chat_log(self) -> list[tuple[str, str, float]]: ...
    @property
    def turn_deadline(self) -> float | None: ...
    @property
    def seed_commitment(self) -> str: ...

    def register(self, name: str, wallet_address: str | None = None) -> RegisteredPlayer: ...
    def get_player(self, player_id: int) -> RegisteredPlayer | None: ...
    def get_player_by_name(self, name: str) -> RegisteredPlayer | None: ...
    def start(self) -> int: ...
    def do_action(
        self,
        player_id: int,
        action: str,
        amount: int | None = None,
        comment: str | None = None,
        reason: str | None = None,
    ) -> str: ...
    def resign(self, player_id: int) -> str: ...
    def add_chat(self, player_name: str, message: str) -> None: ...
    def use_extension(self, player_id: int) -> tuple[float, int] | None: ...
    def get_extensions_remaining(self, player_id: int) -> int: ...
