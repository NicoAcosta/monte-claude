"""Dice-specific Pydantic models for state and spectator responses."""

from __future__ import annotations

from pydantic import BaseModel


class DicePlayerState(BaseModel):
    id: int
    name: str
    chips: int
    resigned: bool
    is_current: bool
    bet: str | None  # their bet this round, if placed
    extensions_remaining: int = 0


class DiceStateResponse(BaseModel):
    game_type: str = "dice"
    started: bool
    game_over: bool
    winner: str | None
    round_number: int
    phase: str  # waiting | betting | reveal | complete
    ante: int
    your_player_id: int
    your_chips: int
    your_bet: str | None
    is_your_turn: bool
    players: list[DicePlayerState]
    # Last round result (only in reveal/complete phase)
    last_dice: list[int] | None = None
    last_total: int | None = None
    last_category: str | None = None
    last_winner_ids: list[int] | None = None
    last_pot: int | None = None
    # Timer
    turn_deadline: float | None = None
    extensions_remaining: int = 0
    # Chat
    chat: list[dict] = []
    state_version: int = 0
    seed_commitment: str = ""


class DiceSpectatorPlayerState(BaseModel):
    id: int
    name: str
    chips: int
    resigned: bool
    is_current: bool
    bet: str | None


class DiceSpectatorResponse(BaseModel):
    game_type: str = "dice"
    started: bool
    game_over: bool
    winner: str | None
    round_number: int
    phase: str
    ante: int
    players: list[DiceSpectatorPlayerState]
    last_dice: list[int] | None = None
    last_total: int | None = None
    last_category: str | None = None
    last_winner_ids: list[int] | None = None
    last_pot: int | None = None
    turn_deadline: float | None = None
    chat: list[dict] = []
    state_version: int = 0
    # Stream fields (optional)
    commentary_text: str | None = None
    stream_id: int | None = None
    stream_title: str | None = None
    stream_host: str | None = None
    stream_created_at: float | None = None
    seed_commitment: str = ""
