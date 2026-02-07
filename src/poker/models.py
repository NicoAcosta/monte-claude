from __future__ import annotations

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    name: str


class RegisterResponse(BaseModel):
    player_id: int
    name: str


class WaitingResponse(BaseModel):
    started: bool
    players: list[PlayerBrief]
    player_count: int


class PlayerBrief(BaseModel):
    id: int
    name: str
    chips: int


class StartResponse(BaseModel):
    message: str
    hand_number: int


class ActionRequest(BaseModel):
    player_id: int
    action: str
    amount: int | None = None
    comment: str | None = None


class PlayerPublicState(BaseModel):
    id: int
    name: str
    chips: int
    current_bet: int
    is_folded: bool
    is_all_in: bool


class RecentAction(BaseModel):
    player: str
    action: str
    amount: int | None = None
    comment: str | None = None


class PlayerComment(BaseModel):
    player: str
    comment: str


class CommentateRequest(BaseModel):
    text: str


class CommentateResponse(BaseModel):
    success: bool


class PlayerStateResponse(BaseModel):
    hand_number: int
    phase: str
    your_cards: list[str]
    community_cards: list[str]
    pot: int
    side_pots: list[SidePotInfo]
    your_chips: int
    your_current_bet: int
    current_turn: int | None
    is_your_turn: bool
    dealer: int
    small_blind_player: int
    big_blind_player: int
    min_raise: int
    amount_to_call: int
    players: list[PlayerPublicState]
    game_over: bool
    winner: str | None
    recent_actions: list[RecentAction]
    player_comments: list[PlayerComment] = []
    commentary_text: str | None = None


class SidePotInfo(BaseModel):
    amount: int
    eligible_players: list[int]


class SpectatorPlayerState(BaseModel):
    id: int
    name: str
    chips: int
    current_bet: int
    is_folded: bool
    is_all_in: bool
    cards: list[str]


class SpectatorResponse(BaseModel):
    hand_number: int
    phase: str
    community_cards: list[str]
    pot: int
    side_pots: list[SidePotInfo]
    current_turn: int | None
    dealer: int
    small_blind_player: int
    big_blind_player: int
    players: list[SpectatorPlayerState]
    game_over: bool
    winner: str | None
    recent_actions: list[RecentAction]
    started: bool
    commentary_text: str | None = None


class ActionResponse(BaseModel):
    success: bool
    message: str


class ErrorResponse(BaseModel):
    detail: str
