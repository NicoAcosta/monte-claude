from __future__ import annotations

from pydantic import BaseModel

# Re-export all generic models from core for backward compatibility
from core.models import (  # noqa: F401
    AccountRegisterRequest,
    AccountRegisterResponse,
    ActionRequest,
    ActionResponse,
    BalanceResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    CommentateRequest,
    CommentateResponse,
    CreateGameRequest,
    CreateGameResponse,
    CreateStreamRequest,
    CreateStreamResponse,
    DepositStatus,
    ErrorResponse,
    EscrowConfigResponse,
    EscrowInfoResponse,
    ExtendResponse,
    FaucetResponse,
    FundingStatusResponse,
    GameEventResponse,
    GameHistoryResponse,
    GameListItem,
    GameListResponse,
    JoinGameRequest,
    JoinGameResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    OffchainPayout,
    OffchainSettlementResponse,
    PayoutEntry,
    PlayerBrief,
    PlayerComment,
    PlayerStatsResponse,
    RecentAction,
    SettlementResponse,
    StartResponse,
    StreamListItem,
    StreamListResponse,
    TimerInfo,
    TokenStatsEntry,
    WaitingResponse,
)


# ── Poker-specific models ─────────────────────────────

class PlayerPublicState(BaseModel):
    id: int
    name: str
    chips: int
    current_bet: int
    is_folded: bool
    is_all_in: bool
    is_resigned: bool = False
    extensions_remaining: int = 0


class SidePotInfo(BaseModel):
    amount: int
    eligible_players: list[int]


class PlayerStateResponse(BaseModel):
    state_version: int
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
    chat_log: list[ChatMessage] = []
    timer: TimerInfo | None = None
    seed_commitment: str = ""


class SpectatorPlayerState(BaseModel):
    id: int
    name: str
    chips: int
    current_bet: int
    is_folded: bool
    is_all_in: bool
    cards: list[str]
    extensions_remaining: int = 0
    is_resigned: bool = False


class SpectatorResponse(BaseModel):
    game_type: str = "poker"
    state_version: int = 0
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
    stream_id: int | None = None
    stream_title: str | None = None
    stream_host: str | None = None
    stream_created_at: float | None = None
    chat_log: list[ChatMessage] = []
    timer: TimerInfo | None = None
    buy_in: int = 0
    buy_in_display: str = ""
    token_symbol: str | None = None
    escrow_address: str | None = None
    mode: str = "offchain"
    max_players: int = 0
    starting_players: int = 0
    action_timeout: float = 30.0
    small_blind: int = 10
    big_blind: int = 20
    game_started_at: float | None = None
    seed_commitment: str = ""


class HandSummaryResponse(BaseModel):
    game_id: int
    hand_number: int
    dealer_id: int
    player_ids: list[int]
    winner_ids: list[int]
    pot: int
    community_cards: str
    timestamp: float
    winner_names: list[str] = []
    winning_cards: dict[str, list[str]] = {}
    result_type: str = "fold"
    token_symbol: str | None = None
    seed_hex: str = ""
    seed_commitment: str = ""


class HandSummariesResponse(BaseModel):
    game_id: int
    hands: list[HandSummaryResponse]


class RecentHandItem(BaseModel):
    game_id: int
    hand_number: int
    winner_ids: list[int]
    winner_names: list[str] = []
    pot: int
    timestamp: float
    winning_cards: dict[str, list[str]] = {}
    result_type: str = "fold"
    token_symbol: str | None = None
    seed_hex: str = ""
    seed_commitment: str = ""


class RecentHandsResponse(BaseModel):
    hands: list[RecentHandItem]
    total: int = 0
