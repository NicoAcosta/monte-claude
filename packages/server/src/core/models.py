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
    game_type: str = "poker"
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


class ActionResponse(BaseModel):
    success: bool
    message: str


class ErrorResponse(BaseModel):
    detail: str


class CreateGameResponse(BaseModel):
    game_id: int
    game_type: str = "poker"
    max_players: int
    token: str | None
    buy_in: int
    buy_in_display: str = ""
    token_symbol: str | None = None
    mode: str


class GameListItem(BaseModel):
    id: int
    game_type: str = "poker"
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
    pcr0_hash: str = ""  # hex-encoded keccak256 of PCR-0 (0x00..00 = dev mode)


class EscrowInfoResponse(BaseModel):
    escrow_address: str
    factory_address: str
    salt: str
    config: EscrowConfigResponse
    admin_signature: str = ""
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
    pcr0: str = ""  # hex-encoded raw PCR-0 (empty in dev mode)


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


# ── Attestation models ────────────────────────────────────


class AttestationResponse(BaseModel):
    document: str  # base64-encoded COSE_Sign1 (source of truth for verifiers)
    module_id: str
    timestamp: int  # ms since epoch
    digest: str  # "SHA384"
    pcrs: dict[str, str]  # {"0": "<hex>", "1": "<hex>", "2": "<hex>"}
    user_data: str | None  # hex
    nonce: str | None  # hex
    server_address: str  # Ethereum address (0x-prefixed checksum)
