"""Poker game router — all poker-specific HTTP routes.

Extracted from game_api/app.py. Mounted with a prefix (e.g. /poker)
by the Game API application.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

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
from poker.game import BIG_BLIND, Game, SMALL_BLIND
from poker.models import (
    ActionRequest,
    ActionResponse,
    ChatMessage,
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
    PlayerComment,
    PlayerPublicState,
    PlayerStateResponse,
    RecentAction,
    SettlementResponse,
    SidePotInfo,
    SpectatorPlayerState,
    SpectatorResponse,
    StartResponse,
    TimerInfo,
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


def _recent_actions(game: Game, include_reason: bool = False) -> list[RecentAction]:
    actions = game.recent_actions
    if game.current_hand:
        actions = game.current_hand.actions
    return [_action_to_recent(a, include_reason) for a in actions[-20:]]


def _action_to_recent(a: Any, include_reason: bool = False) -> RecentAction:
    return RecentAction(
        id=a.id,
        timestamp=a.timestamp,
        player=a.player_name,
        action=a.action,
        amount=a.amount,
        comment=a.comment,
        reason=a.reason if include_reason else None,
    )


def _player_comments(game: Game) -> list[PlayerComment]:
    actions = game.current_hand.actions if game.current_hand else game.recent_actions
    latest: dict[str, str] = {}
    for a in actions:
        if a.comment:
            latest[a.player_name] = a.comment
    return [PlayerComment(player=name, comment=text) for name, text in latest.items()]


def _chat_log(game: Game) -> list[ChatMessage]:
    return [
        ChatMessage(player=name, message=msg, timestamp=ts)
        for name, msg, ts in game.chat_log
    ]


def _timer_info(game: Game, player_id: int = 0) -> TimerInfo | None:
    if not game.started or game.game_over:
        return None
    return TimerInfo(
        action_timeout=game.action_timeout,
        turn_started_at=game.current_hand.turn_started_at if game.current_hand else None,
        deadline=game.turn_deadline,
        extensions_remaining=game.get_extensions_remaining(player_id),
    )


def _build_spectator_response(game: Game, config: GameConfig, **overrides: Any) -> SpectatorResponse:
    prev = game.previous_hand

    if prev is None:
        base = dict(
            hand_number=0,
            phase="waiting",
            community_cards=[],
            pot=0,
            side_pots=[],
            current_turn=None,
            dealer=0,
            small_blind_player=0,
            big_blind_player=0,
            players=[
                SpectatorPlayerState(
                    id=p.id, name=p.name, chips=p.chips,
                    current_bet=0, is_folded=False, is_all_in=False, cards=[],
                    extensions_remaining=game.get_extensions_remaining(p.id) if game.started else 0,
                    is_resigned=p.resigned,
                )
                for p in game._players
            ],
            game_over=game.game_over,
            winner=game.winner,
            recent_actions=[],
            started=game.started,
            chat_log=_chat_log(game),
            timer=_timer_info(game),
            buy_in=config.buy_in,
            buy_in_display=config.buy_in_display,
            token_symbol=config.token_symbol,
            escrow_address=config.escrow_address,
            mode=config.mode or GameMode.OFFCHAIN,
            max_players=config.max_players,
            starting_players=len(game._players),
            action_timeout=game.action_timeout,
            small_blind=SMALL_BLIND,
            big_blind=BIG_BLIND,
            game_started_at=game.started_at,
            seed_commitment=game.seed_commitment,
        )
        base.update(overrides)
        return SpectatorResponse(**base)

    side_pots = prev.get_side_pots_info()

    base = dict(
        hand_number=game.hand_number if game.game_over else game.hand_number - 1,
        phase=prev.phase,
        community_cards=[str(c) for c in prev.community_cards],
        pot=prev.pot,
        side_pots=[
            SidePotInfo(amount=sp.amount, eligible_players=list(sp.eligible_player_ids))
            for sp in side_pots
        ],
        current_turn=None,
        dealer=prev.players[prev.dealer_index].id,
        small_blind_player=prev.players[prev._sb_index()].id,
        big_blind_player=prev.players[prev._bb_index()].id,
        players=[
            SpectatorPlayerState(
                id=p.id,
                name=p.name,
                chips=p.chips,
                current_bet=p.current_bet,
                is_folded=p.is_folded,
                is_all_in=p.is_all_in,
                cards=[str(c) for c in p.hole_cards],
                extensions_remaining=game.get_extensions_remaining(p.id),
                is_resigned=getattr(game.get_player(p.id), 'resigned', False),
            )
            for p in prev.players
        ],
        game_over=game.game_over,
        winner=game.winner,
        recent_actions=[_action_to_recent(a, include_reason=True) for a in prev.actions],
        started=game.started,
        chat_log=_chat_log(game),
        timer=_timer_info(game),
        buy_in=config.buy_in,
        buy_in_display=config.buy_in_display,
        token_symbol=config.token_symbol,
        escrow_address=config.escrow_address,
        mode=config.mode or GameMode.OFFCHAIN,
        max_players=config.max_players,
        starting_players=len(game._players),
        action_timeout=game.action_timeout,
        small_blind=SMALL_BLIND,
        big_blind=BIG_BLIND,
        game_started_at=game.started_at,
        seed_commitment=game.seed_commitment,
    )
    base.update(overrides)
    return SpectatorResponse(**base)


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
    player_id = rp.id
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    game._check_timeout()

    hand = game.current_hand

    if hand is None:
        return PlayerStateResponse(
            state_version=game.state_version,
            hand_number=game.hand_number,
            phase="complete",
            your_cards=[],
            community_cards=[],
            pot=0,
            side_pots=[],
            your_chips=rp.chips,
            your_current_bet=0,
            current_turn=None,
            is_your_turn=False,
            dealer=0,
            small_blind_player=0,
            big_blind_player=0,
            min_raise=0,
            amount_to_call=0,
            players=[],
            game_over=game.game_over,
            winner=game.winner,
            recent_actions=_recent_actions(game),
            player_comments=_player_comments(game),
            chat_log=_chat_log(game),
            seed_commitment=game.seed_commitment,
        )

    hand_player = hand._get_player(player_id)
    your_cards = [str(c) for c in hand_player.hole_cards] if hand_player else []
    your_chips = hand_player.chips if hand_player else rp.chips
    your_bet = hand_player.current_bet if hand_player else 0

    current_turn_id = hand.current_player.id if hand.current_player else None

    side_pots = hand.get_side_pots_info()

    return PlayerStateResponse(
        state_version=game.state_version,
        hand_number=game.hand_number,
        phase=hand.phase,
        your_cards=your_cards,
        community_cards=[str(c) for c in hand.community_cards],
        pot=hand.pot,
        side_pots=[
            SidePotInfo(amount=sp.amount, eligible_players=list(sp.eligible_player_ids))
            for sp in side_pots
        ],
        your_chips=your_chips,
        your_current_bet=your_bet,
        current_turn=current_turn_id,
        is_your_turn=current_turn_id == player_id,
        dealer=game.get_dealer_player_id(),
        small_blind_player=game.get_sb_player_id(),
        big_blind_player=game.get_bb_player_id(),
        min_raise=hand.get_min_raise(),
        amount_to_call=hand.get_amount_to_call(player_id),
        players=[
            PlayerPublicState(
                id=p.id,
                name=p.name,
                chips=p.chips,
                current_bet=p.current_bet,
                is_folded=p.is_folded,
                is_all_in=p.is_all_in,
                is_resigned=getattr(game.get_player(p.id), 'resigned', False),
                extensions_remaining=game.get_extensions_remaining(p.id),
            )
            for p in hand.players
        ],
        game_over=game.game_over,
        winner=game.winner,
        recent_actions=_recent_actions(game),
        player_comments=_player_comments(game),
        chat_log=_chat_log(game),
        timer=_timer_info(game, player_id),
        seed_commitment=game.seed_commitment,
    )


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
    return _build_spectator_response(game, config)


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
