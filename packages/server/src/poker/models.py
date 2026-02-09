from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AccountRegisterRequest(BaseModel):
    username: str


class AccountRegisterResponse(BaseModel):
    api_key: str
    username: str


class CreateGameRequest(BaseModel):
    max_players: int = Field(default=0, ge=0, le=10)
    token: str | None = None
    buy_in: int = Field(default=0, ge=0)
    token_decimals: int = Field(default=0, ge=0, le=18)
    token_symbol: str | None = None
    mode: Literal["onchain", "offchain"] | None = None
    action_timeout: float | None = Field(default=None, gt=0, le=600)
    extensions_per_player: int | None = Field(default=None, ge=0, le=20)

    @field_validator("token")
    @classmethod
    def validate_token_address(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.match(r"^0x[a-fA-F0-9]{40}$", v):
            raise ValueError("Token must be a valid hex address (0x + 40 hex chars)")
        return v


class JoinGameRequest(BaseModel):
    wallet_address: str | None = None


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
    expected_version: int | None = None


class PlayerPublicState(BaseModel):
    id: int
    name: str
    chips: int
    current_bet: int
    is_folded: bool
    is_all_in: bool
    is_resigned: bool = False
    extensions_remaining: int = 0


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
    extensions_remaining: int = 0
    is_resigned: bool = False


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


class ActionResponse(BaseModel):
    success: bool
    message: str


class ErrorResponse(BaseModel):
    detail: str


class CreateGameResponse(BaseModel):
    game_id: int
    max_players: int
    token: str | None
    buy_in: int
    buy_in_display: str = ""
    token_symbol: str | None = None
    mode: str


class GameListItem(BaseModel):
    id: int
    player_count: int
    player_names: list[str]
    started: bool
    game_over: bool
    winner: str | None
    hand_number: int
    max_players: int = 0
    token: str | None = None
    buy_in: int = 0
    buy_in_display: str = ""
    token_symbol: str | None = None
    funded: bool = False
    mode: str = "offchain"


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
    winner_names: list[str] = []
    winning_cards: dict[str, list[str]] = {}
    result_type: str = "fold"
    token_symbol: str | None = None


class HandSummariesResponse(BaseModel):
    game_id: int
    hands: list[HandSummaryResponse]


class TokenStatsEntry(BaseModel):
    token_symbol: str
    total_winnings: int
    biggest_pot_won: int
    hands_played: int
    hands_won: int


class PlayerStatsResponse(BaseModel):
    username: str
    games_played: int
    hands_played: int
    hands_won: int
    total_winnings: int
    biggest_pot_won: int
    token_stats: list[TokenStatsEntry] = []


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    games_played: int
    hands_won: int
    win_rate: float
    total_winnings: int
    biggest_pot_won: int
    token_stats: list[TokenStatsEntry] = []


class LeaderboardResponse(BaseModel):
    players: list[LeaderboardEntry]
    total: int = 0


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


class RecentHandsResponse(BaseModel):
    hands: list[RecentHandItem]
    total: int = 0


# ── Stream models ──────────────────────────────────────

class CreateStreamRequest(BaseModel):
    title: str


class CreateStreamResponse(BaseModel):
    stream_id: int


class StreamListItem(BaseModel):
    id: int
    game_id: int
    host: str
    title: str


class StreamListResponse(BaseModel):
    streams: list[StreamListItem]


# ── Escrow models ──────────────────────────────────────

class DepositStatus(BaseModel):
    address: str
    deposited: bool
    player_name: str | None = None


class EscrowConfigResponse(BaseModel):
    token: str
    admin: str
    rake_beneficiary: str
    deposit_amount: int
    rake_bps: int
    funding_deadline: int
    settlement_deadline: int
    participants: list[str]


class EscrowInfoResponse(BaseModel):
    escrow_address: str
    factory_address: str
    salt: str
    config: EscrowConfigResponse
    calldata_create_and_deposit: str
    calldata_deposit: dict[str, str]
    funding_deadline: int
    settlement_deadline: int


class FundingStatusResponse(BaseModel):
    all_deposited: bool
    deposits: list[DepositStatus]


class PayoutEntry(BaseModel):
    address: str
    amount: int


class SettlementResponse(BaseModel):
    payouts: list[PayoutEntry]
    signature: str
    escrow_address: str


# ── Off-chain bankroll models ─────────────────────────

class FaucetResponse(BaseModel):
    success: bool
    new_balance: int
    next_claim_at: str


class BalanceResponse(BaseModel):
    username: str
    balance: int


class OffchainPayout(BaseModel):
    username: str
    amount: int


class OffchainSettlementResponse(BaseModel):
    payouts: list[OffchainPayout]
