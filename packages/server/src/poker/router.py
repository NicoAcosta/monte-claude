"""Poker game router — all poker-specific HTTP routes.

Extracted from game_api/app.py. Mounted with a prefix (e.g. /poker)
by the Game API application.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from core.account_store import Account, AccountStore
from core.audit import EscrowAuditStore
from core.balance_store import BalanceStore
from core import escrow_service, game_service, settlement_service
from core.game_config import GameConfig
from core.game_manager import GameManager
from core.game_metadata_store import GameMetadataStore
from core.game_mode import GameMode
from core.state_builders import build_poker_player_state, build_poker_spectator_state
from poker.game import Game
from poker.models import (
    ActionRequest,
    ActionResponse,
    ChatRequest,
    ChatResponse,
    CreateGameRequest,
    CreateGameResponse,
    DepositStatus,
    EscrowConfigResponse,
    EscrowDepositGuide,
    EscrowGuide,
    EscrowInfoResponse,
    EscrowTxStep,
    ExtendResponse,
    FundingStatusResponse,
    JoinGameRequest,
    JoinGameResponse,
    OffchainPayout,
    OffchainSettlementResponse,
    PayoutEntry,
    PlayerBrief,
    PlayerStateResponse,
    SettlementResponse,
    SpectatorResponse,
    StartResponse,
    WaitingResponse,
)

_log = logging.getLogger("poker.router")

router = APIRouter()

# ── Dependency injection (set by game_api.app during startup) ─────

manager: GameManager | None = None
balance_store: BalanceStore | None = None
account_store: AccountStore | None = None
metadata_store: GameMetadataStore | None = None
escrow_audit: EscrowAuditStore | None = None
_auth_callable: Callable[..., Account] | None = None

# Matches the header name used by core.auth so FastAPI generates correct OpenAPI spec
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_auth(api_key: str | None = Security(_api_key_header)) -> Account:
    """Auth dependency wrapper — delegates to the configured auth callable."""
    assert _auth_callable is not None, "Router not configured — call configure() first"
    return _auth_callable(api_key)


def configure(
    *,
    mgr: GameManager,
    bal: BalanceStore,
    acc: AccountStore,
    meta: GameMetadataStore,
    esc_audit: EscrowAuditStore,
    auth_dep: Callable[..., Account],
) -> None:
    """Inject shared stores and auth dependency from the application layer."""
    global manager, balance_store, account_store, metadata_store, escrow_audit, _auth_callable
    manager = mgr
    balance_store = bal
    account_store = acc
    metadata_store = meta
    escrow_audit = esc_audit
    _auth_callable = auth_dep


# ── Helpers ───────────────────────────────────────────────────────


def _get_game_or_404(game_id: str) -> tuple[Game, GameConfig]:
    assert manager is not None, "Router not configured — call configure() first"
    game = manager.get_game(game_id)
    config = manager.get_config(game_id)
    if game is None or config is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.game_type != "poker":
        raise HTTPException(status_code=404, detail="Game not found")
    return game, config  # type: ignore[return-value]


# ── Game CRUD routes ──────────────────────────────────────────────


@router.post("/games", response_model=CreateGameResponse)
def create_game(req: CreateGameRequest) -> CreateGameResponse:
    assert manager is not None and balance_store is not None

    try:
        mode = game_service.validate_mode(req.mode, req.token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def _on_game_over(g: Game, c: GameConfig) -> None:
        settlement_service.settle_offchain_game(g, c, balance_store)
        manager.cleanup_completed()

    try:
        game_id, game, config = game_service.create_game(
            manager, req.max_players, req.token, req.buy_in, mode,
            token_decimals=req.token_decimals,
            token_symbol=req.token_symbol,
            on_game_over=_on_game_over,
            action_timeout=req.action_timeout,
            extensions_per_player=req.extensions_per_player,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CreateGameResponse(
        game_id=game_id,
        max_players=config.max_players,
        token=config.token,
        buy_in=config.buy_in,
        buy_in_display=config.buy_in_display,
        token_symbol=config.token_symbol,
        mode=config.mode or GameMode.OFFCHAIN,
    )


# ── Join / Waiting / Start ────────────────────────────────────────


@router.post("/{game_id}/join", response_model=JoinGameResponse)
def join_game(game_id: str, req: JoinGameRequest, account: Account = Depends(_require_auth)):
    assert manager is not None and balance_store is not None and metadata_store is not None
    game, config = _get_game_or_404(game_id)
    try:
        player = game_service.join_game(
            game=game,
            config=config,
            username=account.username,
            wallet_address=req.wallet_address,
            balance_store=balance_store,
            recorder=manager.get_recorder(game_id),
            metadata_store=metadata_store,
            game_id=game_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JoinGameResponse(player_id=player.id, name=player.name)


@router.get("/{game_id}/waiting", response_model=WaitingResponse)
def waiting(game_id: str) -> WaitingResponse:
    game, _config = _get_game_or_404(game_id)
    return WaitingResponse(
        started=game.started,
        players=[
            PlayerBrief(id=p.id, name=p.name, chips=p.chips)
            for p in game._players
        ],
        player_count=game.player_count,
    )


@router.post("/{game_id}/start", response_model=StartResponse)
def start(game_id: str, account: Account = Depends(_require_auth)):
    assert manager is not None and metadata_store is not None
    game, config = _get_game_or_404(game_id)
    if game.get_player_by_name(account.username) is None:
        raise HTTPException(status_code=403, detail="Not a player in this game")

    try:
        hand_num = game_service.start_game(
            game=game,
            config=config,
            recorder=manager.get_recorder(game_id),
            metadata_store=metadata_store,
            game_id=game_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StartResponse(message="Game started", hand_number=hand_num)


# ── Game state & action routes ────────────────────────────────────


@router.get("/{game_id}/state", response_model=PlayerStateResponse)
def state(game_id: str, account: Account = Depends(_require_auth)):
    game, config = _get_game_or_404(game_id)
    rp = game.get_player_by_name(account.username)
    if rp is None:
        raise HTTPException(status_code=403, detail="Not a player in this game")
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    game._check_timeout()

    return build_poker_player_state(game, config, rp.id)


@router.post("/{game_id}/action", response_model=ActionResponse)
def action(game_id: str, req: ActionRequest, account: Account = Depends(_require_auth)):
    game, config = _get_game_or_404(game_id)
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    if req.expected_version is not None and req.expected_version != game.state_version:
        raise HTTPException(
            status_code=409,
            detail=f"State version conflict: expected {req.expected_version}, current {game.state_version}",
        )

    game._check_timeout()

    player = game.get_player_by_name(account.username)
    if player is None:
        raise HTTPException(status_code=404, detail="Not a player in this game")

    if req.comment is not None and len(req.comment) > 140:
        raise HTTPException(status_code=400, detail="Comment too long (max 140 chars)")
    if req.reason is not None and len(req.reason) > 500:
        raise HTTPException(status_code=400, detail="Reason too long (max 500 chars)")

    result = game.do_action(player.id, req.action, req.amount, comment=req.comment, reason=req.reason)
    if result == "ok":
        return ActionResponse(success=True, message="Action accepted")
    raise HTTPException(status_code=400, detail=result)


@router.post("/{game_id}/resign", response_model=ActionResponse)
def resign(game_id: str, account: Account = Depends(_require_auth)):
    game, config = _get_game_or_404(game_id)
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    player = game.get_player_by_name(account.username)
    if player is None:
        raise HTTPException(status_code=404, detail="Not a player in this game")

    result = game.resign(player.id)
    if result == "ok":
        return ActionResponse(success=True, message="Resigned from game")
    raise HTTPException(status_code=400, detail=result)


# ── Spectator ─────────────────────────────────────────────────────


@router.get("/{game_id}/spectator", response_model=SpectatorResponse)
def spectator(game_id: str) -> SpectatorResponse:
    game, config = _get_game_or_404(game_id)
    game._check_timeout()
    return build_poker_spectator_state(game, config)


# ── Chat & Timer routes ───────────────────────────────────────────


@router.post("/{game_id}/chat", response_model=ChatResponse)
def chat(game_id: str, req: ChatRequest, account: Account = Depends(_require_auth)):
    game, _ = _get_game_or_404(game_id)
    player = game.get_player_by_name(account.username)
    if player is None:
        raise HTTPException(status_code=403, detail="Not a player in this game")
    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(msg) > 140:
        raise HTTPException(status_code=400, detail="Message too long (max 140 chars)")
    game.add_chat(player.name, msg)
    return ChatResponse(success=True)


@router.post("/{game_id}/extend", response_model=ExtendResponse)
def extend(game_id: str, account: Account = Depends(_require_auth)):
    game, _ = _get_game_or_404(game_id)
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    player = game.get_player_by_name(account.username)
    if player is None:
        raise HTTPException(status_code=403, detail="Not a player in this game")

    result = game.use_extension(player.id)
    if result is None:
        game._check_timeout()
        raise HTTPException(status_code=400, detail="Cannot extend (not your turn or no extensions left)")

    new_deadline, remaining = result
    return ExtendResponse(success=True, new_deadline=new_deadline, extensions_remaining=remaining)


# ── Escrow routes ─────────────────────────────────────────────────


@router.get("/{game_id}/escrow", response_model=EscrowInfoResponse)
def escrow_info(game_id: str) -> EscrowInfoResponse:
    game, config = _get_game_or_404(game_id)
    if config.mode != GameMode.ONCHAIN:
        raise HTTPException(status_code=400, detail="Escrow only available for on-chain games")

    try:
        info = escrow_service.get_escrow_info(game, config, audit=escrow_audit, game_id=game_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="On-chain escrow is not configured on this server")

    cfg = info["config"]
    guide_data = info["guide"]
    guide = EscrowGuide(
        first_depositor=EscrowDepositGuide(
            steps=[EscrowTxStep(**s) for s in guide_data["first_depositor"]],
        ),
        subsequent_depositor=EscrowDepositGuide(
            steps=[EscrowTxStep(**s) for s in guide_data["subsequent_depositor"]],
        ),
        verification=guide_data["verification"],
        notes=guide_data["notes"],
    )
    return EscrowInfoResponse(
        escrow_address=info["escrow_address"],
        factory_address=info["factory_address"],
        salt=info["salt"],
        config=EscrowConfigResponse(
            token=cfg.token,
            admin=cfg.admin,
            rake_beneficiary=cfg.rake_beneficiary,
            deposit_amount=cfg.deposit_amount,
            rake_bps=cfg.rake_bps,
            funding_deadline=cfg.funding_deadline,
            settlement_deadline=cfg.settlement_deadline,
            participants=list(cfg.participants),
            pcr0_hash="0x" + cfg.pcr0_hash.hex(),
        ),
        admin_signature=info["admin_signature"],
        calldata_create_and_deposit=info["calldata_create_and_deposit"],
        calldata_deposit=info["calldata_deposit"],
        calldata_approve_factory=info["calldata_approve_factory"],
        calldata_approve_escrow=info["calldata_approve_escrow"],
        funding_deadline=info["funding_deadline"],
        settlement_deadline=info["settlement_deadline"],
        guide=guide,
    )


@router.get("/{game_id}/funding", response_model=FundingStatusResponse)
def funding_status(game_id: str) -> FundingStatusResponse:
    game, config = _get_game_or_404(game_id)
    if config.mode != GameMode.ONCHAIN:
        raise HTTPException(status_code=400, detail="Funding status only available for on-chain games")

    try:
        result = escrow_service.check_funding(game, config, audit=escrow_audit, game_id=game_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FundingStatusResponse(
        all_deposited=result["all_deposited"],
        deposits=[
            DepositStatus(
                address=addr,
                deposited=deposited,
                player_name=result["wallet_to_name"].get(addr.lower()),
            )
            for addr, deposited in result["statuses"]
        ],
    )


@router.get("/{game_id}/settlement", response_model=SettlementResponse)
def settlement(game_id: str) -> SettlementResponse:
    game, config = _get_game_or_404(game_id)
    if config.mode != GameMode.ONCHAIN:
        raise HTTPException(status_code=400, detail="Settlement only available for on-chain games")

    try:
        result = escrow_service.get_settlement(game, config, audit=escrow_audit, game_id=game_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="On-chain escrow is not configured on this server")

    pcr0_bytes = result.get("pcr0", b"")
    return SettlementResponse(
        payouts=[PayoutEntry(address=addr, amount=amt) for addr, amt in result["payouts"]],
        signature=result["signature"],
        escrow_address=result["escrow_address"],
        pcr0="0x" + pcr0_bytes.hex() if pcr0_bytes else "",
    )


# ── Off-chain settlement ─────────────────────────────────────────


@router.get("/{game_id}/offchain-settlement", response_model=OffchainSettlementResponse)
def offchain_settlement(game_id: str) -> OffchainSettlementResponse:
    game, config = _get_game_or_404(game_id)
    if config.mode != GameMode.OFFCHAIN:
        raise HTTPException(status_code=400, detail="Not an off-chain game")
    if not game.game_over:
        raise HTTPException(status_code=400, detail="Game is not over yet")
    if config.offchain_settlement is None:
        raise HTTPException(status_code=400, detail="Settlement not yet computed")

    return OffchainSettlementResponse(
        payouts=[
            OffchainPayout(username=name, amount=amt)
            for name, amt in config.offchain_settlement
        ]
    )
