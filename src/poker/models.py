from __future__ import annotations

from pydantic import BaseModel


class AccountRegisterRequest(BaseModel):
    username: str


class AccountRegisterResponse(BaseModel):
    api_key: str
    username: str


class JoinGameResponse(BaseModel):
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
    action: str
    amount: int | None = None
    comment: str | None = None
    reason: str | None = None


class PlayerPublicState(BaseModel):
    id: int
    name: str
    chips: int
    current_bet: int
    is_folded: bool
    is_all_in: bool


class RecentAction(BaseModel):
    id: int
    timestamp: float
    player: str
    action: str
    amount: int | None = None
    comment: str | None = None
    reason: str | None = None


class PlayerComment(BaseModel):
    player: str
    comment: str


class CommentateRequest(BaseModel):
    text: str


class CommentateResponse(BaseModel):
    success: bool


class ChatMessage(BaseModel):
    player: str
    message: str
    timestamp: float


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    success: bool


class TimerInfo(BaseModel):
    action_timeout: float
    turn_started_at: float | None
    deadline: float | None
    extensions_remaining: int


class ExtendResponse(BaseModel):
    success: bool
    new_deadline: float
    extensions_remaining: int


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
    chat_log: list[ChatMessage] = []
    timer: TimerInfo | None = None


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
    chat_log: list[ChatMessage] = []
    timer: TimerInfo | None = None


class ActionResponse(BaseModel):
    success: bool
    message: str


class ErrorResponse(BaseModel):
    detail: str


class CreateGameResponse(BaseModel):
    game_id: int


class GameListItem(BaseModel):
    id: int
    player_count: int
    player_names: list[str]
    started: bool
    game_over: bool
    winner: str | None
    hand_number: int


class GameListResponse(BaseModel):
    games: list[GameListItem]


# ── History models ──────────────────────────────────────

class GameEventResponse(BaseModel):
    game_id: int
    event_type: str
    timestamp: float
    hand_number: int
    data: str
    sequence: int


class GameHistoryResponse(BaseModel):
    game_id: int
    events: list[GameEventResponse]


class HandSummaryResponse(BaseModel):
    game_id: int
    hand_number: int
    dealer_id: int
    player_ids: list[int]
    winner_ids: list[int]
    pot: int
    community_cards: str
    timestamp: float


class HandSummariesResponse(BaseModel):
    game_id: int
    hands: list[HandSummaryResponse]


class PlayerStatsResponse(BaseModel):
    username: str
    games_played: int
    hands_played: int
    hands_won: int
    total_winnings: int
    biggest_pot_won: int
