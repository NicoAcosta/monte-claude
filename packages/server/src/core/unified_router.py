"""Unified game router — game-type-agnostic HTTP routes.

Mounted at /api/games by game_api/app.py.  Dispatches to poker- or
dice-specific response builders based on game.game_type.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import APIKeyHeader

from core.account_store import Account, AccountStore
from core.audit import EscrowAuditStore
from core.balance_store import BalanceStore
from core.snapshot_buffer import SnapshotBuffer
from core import escrow_service, game_service, settlement_service
from core.game_config import GameConfig
from core.game_manager import GameManager
from core.game_metadata_store import GameMetadataStore
from core.game_mode import GameMode
from core.game_protocol import GameProtocol
from core.models import (
    ActionRequest,
    ActionResponse,
    ChatRequest,
    ChatResponse,
    CreateGameRequest,
    CreateGameResponse,
    DepositStatus,
    EscrowConfigResponse,
    EscrowInfoResponse,
    ExtendResponse,
    FundingStatusResponse,
    JoinGameRequest,
    JoinGameResponse,
    OffchainPayout,
    OffchainSettlementResponse,
    PayoutEntry,
    PlayerBrief,
    SettlementResponse,
    StartResponse,
    WaitingResponse,
)

_log = logging.getLogger("game.unified_router")

router = APIRouter()

# ── Dependency injection (set by game_api.app during startup) ─────

manager: GameManager | None = None
balance_store: BalanceStore | None = None
account_store: AccountStore | None = None
metadata_store: GameMetadataStore | None = None
escrow_audit: EscrowAuditStore | None = None
snapshot_buffer: SnapshotBuffer | None = None
_auth_callable: Callable[..., Account] | None = None

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_auth(api_key: str | None = Security(_api_key_header)) -> Account:
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
    snapshots: SnapshotBuffer | None = None,
) -> None:
    global manager, balance_store, account_store, metadata_store, escrow_audit, snapshot_buffer, _auth_callable
    manager = mgr
    balance_store = bal
    account_store = acc
    metadata_store = meta
    escrow_audit = esc_audit
    snapshot_buffer = snapshots
    _auth_callable = auth_dep


# ── Helpers ───────────────────────────────────────────────────────


def _get_game_or_404(game_id: int) -> tuple[GameProtocol, GameConfig]:
    """Resolve any game type by ID."""
    assert manager is not None
    game = manager.get_game(game_id)
    config = manager.get_config(game_id)
    if game is None or config is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game, config


def _get_poker_game_or_404(game_id: int) -> tuple[GameProtocol, GameConfig]:
    """Resolve a game, requiring it to be poker."""
    game, config = _get_game_or_404(game_id)
    if game.game_type != "poker":
        raise HTTPException(status_code=400, detail="This endpoint is only available for poker games")
    return game, config


# ── Game CRUD ─────────────────────────────────────────────────────


@router.post("", response_model=CreateGameResponse)
def create_game(req: CreateGameRequest) -> CreateGameResponse:
    assert manager is not None and balance_store is not None

    game_type = req.game_type

    try:
        mode = game_service.infer_mode(req.mode, req.token, game_type=game_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def _on_game_over(g: GameProtocol, c: GameConfig) -> None:
        settlement_service.settle_offchain_game(g, c, balance_store)
        manager.cleanup_completed()

    try:
        game_id, game, config = game_service.create_game(
            manager, req.max_players, req.token, req.buy_in, mode,
            game_type=game_type,
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
        game_type=game_type,
        max_players=config.max_players,
        token=config.token,
        buy_in=config.buy_in,
        buy_in_display=config.buy_in_display,
        token_symbol=config.token_symbol,
        mode=config.mode or GameMode.OFFCHAIN,
    )


# ── Join / Waiting / Start ────────────────────────────────────────


@router.post("/{game_id}/join", response_model=JoinGameResponse)
def join_game(game_id: int, req: JoinGameRequest, account: Account = Depends(_require_auth)):
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
def waiting(game_id: int) -> WaitingResponse:
    game, _config = _get_game_or_404(game_id)
    return WaitingResponse(
        started=game.started,
        players=[
            PlayerBrief(id=p.id, name=p.name, chips=p.chips)
            for p in game.players
        ],
        player_count=game.player_count,
    )


@router.post("/{game_id}/start", response_model=StartResponse)
def start(game_id: int, account: Account = Depends(_require_auth)):
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


# ── State ─────────────────────────────────────────────────────────


@router.get("/{game_id}/state")
def state(game_id: int, account: Account = Depends(_require_auth)):
    game, config = _get_game_or_404(game_id)
    rp = game.get_player_by_name(account.username)
    if rp is None:
        raise HTTPException(status_code=403, detail="Not a player in this game")
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    game._check_timeout()

    if game.game_type == "dice":
        from dice.router import state as dice_state_impl
        # Dice state builder uses the game directly
        return _build_dice_state(game, rp)
    return _build_poker_state(game, config, rp)


def _build_poker_state(game: GameProtocol, config: GameConfig, rp: Any) -> Any:
    """Build poker-specific player state response."""
    from poker.models import (
        PlayerPublicState,
        PlayerStateResponse,
        SidePotInfo,
    )
    from poker.router import _recent_actions, _player_comments, _chat_log, _timer_info

    player_id = rp.id
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
    )


def _build_dice_state(game: GameProtocol, rp: Any) -> Any:
    """Build dice-specific player state response."""
    from core.models import ChatMessage
    from dice.models import DicePlayerState, DiceStateResponse

    current = game.current_player
    bets = game.bets
    result = game.last_result

    return DiceStateResponse(
        started=game.started,
        game_over=game.game_over,
        winner=game.winner,
        round_number=game.hand_number,
        phase=game.phase,
        ante=game.ante,
        your_player_id=rp.id,
        your_chips=rp.chips,
        your_bet=bets.get(rp.id),
        is_your_turn=current is not None and current.id == rp.id,
        players=[
            DicePlayerState(
                id=p.id,
                name=p.name,
                chips=p.chips,
                resigned=p.resigned,
                is_current=current is not None and current.id == p.id,
                bet=bets.get(p.id),
                extensions_remaining=game.get_extensions_remaining(p.id),
            )
            for p in game.players
        ],
        last_dice=list(result.dice) if result else None,
        last_total=result.total if result else None,
        last_category=result.category if result else None,
        last_winner_ids=list(result.winner_ids) if result else None,
        last_pot=result.pot if result else None,
        turn_deadline=game.turn_deadline,
        extensions_remaining=game.get_extensions_remaining(rp.id),
        chat=[
            ChatMessage(player=name, message=msg, timestamp=ts)
            for name, msg, ts in game.chat_log
        ],
        state_version=game.state_version,
    )


# ── Action / Resign ──────────────────────────────────────────────


@router.post("/{game_id}/action", response_model=ActionResponse)
def action(game_id: int, req: ActionRequest, account: Account = Depends(_require_auth)):
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
def resign(game_id: int, account: Account = Depends(_require_auth)):
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


@router.get("/{game_id}/spectator")
def spectator(game_id: int):
    game, config = _get_game_or_404(game_id)
    game._check_timeout()
    if snapshot_buffer is not None:
        delayed = snapshot_buffer.get_delayed_latest(game_id)
        if delayed is not None:
            return delayed
        # Snapshot buffer is configured but no delayed data yet —
        # show previous hand or waiting state (never live current hand,
        # which would reveal hole cards to spectators in real time).
        return _build_spectator_for_game(game, config, skip_live=True)
    return _build_spectator_for_game(game, config)


@router.get("/{game_id}/spectator/snapshots")
def spectator_snapshots(game_id: int, after: int = Query(0)) -> list[dict]:
    _get_game_or_404(game_id)
    if snapshot_buffer is None:
        raise HTTPException(status_code=404, detail="Snapshots not available")
    return snapshot_buffer.get_since(game_id, after)


def _build_spectator_for_game(game: GameProtocol, config: GameConfig, *, skip_live: bool = False, **overrides: Any) -> Any:
    """Dispatch to the correct spectator response builder based on game type.

    skip_live: When True, skip the "live hand in progress" case and only show
    the previous completed hand or waiting state.  Used when the snapshot buffer
    is active but no delayed data is available yet, to avoid revealing hole cards
    to spectators in real time.
    """
    if game.game_type == "dice":
        from dice.router import _build_spectator_response as _build_dice_spectator
        return _build_dice_spectator(game, config, skip_live=skip_live, **overrides)
    from poker.router import _build_spectator_response as _build_poker_spectator
    return _build_poker_spectator(game, config, skip_live=skip_live, **overrides)


# ── Chat & Timer ─────────────────────────────────────────────────


@router.post("/{game_id}/chat", response_model=ChatResponse)
def chat(game_id: int, req: ChatRequest, account: Account = Depends(_require_auth)):
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
def extend(game_id: int, account: Account = Depends(_require_auth)):
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


# ── Poker-only: Escrow / Funding / Settlement ────────────────────


@router.get("/{game_id}/escrow", response_model=EscrowInfoResponse)
def escrow_info(game_id: int) -> EscrowInfoResponse:
    game, config = _get_poker_game_or_404(game_id)
    if config.mode != GameMode.ONCHAIN:
        raise HTTPException(status_code=400, detail="Escrow only available for on-chain games")

    try:
        info = escrow_service.get_escrow_info(game, config, audit=escrow_audit, game_id=game_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="On-chain escrow is not configured on this server")

    cfg = info["config"]
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
        ),
        calldata_create_and_deposit=info["calldata_create_and_deposit"],
        calldata_deposit=info["calldata_deposit"],
        funding_deadline=info["funding_deadline"],
        settlement_deadline=info["settlement_deadline"],
    )


@router.get("/{game_id}/funding", response_model=FundingStatusResponse)
def funding_status(game_id: int) -> FundingStatusResponse:
    game, config = _get_poker_game_or_404(game_id)
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
def settlement(game_id: int) -> SettlementResponse:
    game, config = _get_poker_game_or_404(game_id)
    if config.mode != GameMode.ONCHAIN:
        raise HTTPException(status_code=400, detail="Settlement only available for on-chain games")

    try:
        result = escrow_service.get_settlement(game, config, audit=escrow_audit, game_id=game_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="On-chain escrow is not configured on this server")

    return SettlementResponse(
        payouts=[PayoutEntry(address=addr, amount=amt) for addr, amt in result["payouts"]],
        signature=result["signature"],
        escrow_address=result["escrow_address"],
    )


@router.get("/{game_id}/offchain-settlement", response_model=OffchainSettlementResponse)
def offchain_settlement(game_id: int) -> OffchainSettlementResponse:
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
