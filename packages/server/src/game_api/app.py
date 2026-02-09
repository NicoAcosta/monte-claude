"""Game API — all writes + live state reads (port 8001)."""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from prometheus_fastapi_instrumentator import Instrumentator

from core.logging_config import configure_logging, RequestContextMiddleware

configure_logging()

_log = logging.getLogger("poker.game_api")

from core.account_store import Account, AccountStore
from core.audit import AuthAuditStore, EscrowAuditStore
from core.auth import make_auth_dependency
from core.balance_store import BalanceStore
from core.db import get_pool
from poker.game import BIG_BLIND, Game, SMALL_BLIND
from core.game_config import GameConfig
from core.game_mode import GameMode
from core.game_manager import GameManager
from core.game_metadata_store import GameMetadataStore
from core.game_recorder import GameRecorder
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore
from poker.models import (
    ActionRequest,
    ActionResponse,
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
    PlayerComment,
    PlayerPublicState,
    PlayerStateResponse,
    RecentAction,
    SettlementResponse,
    SidePotInfo,
    SpectatorPlayerState,
    SpectatorResponse,
    StartResponse,
    StreamListItem,
    StreamListResponse,
    TimerInfo,
    WaitingResponse,
)
from core.stream_store import StreamStore
from core import escrow_service, game_service, settlement_service

app = FastAPI(title="Monteclaude — Game API", version="0.1.0")
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception):
    _log.exception("unhandled_exception path=%s", request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.get("/health")
def health():
    pool = get_pool()
    stats = pool.get_stats()
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "healthy" if db_ok else "degraded",
        "db": db_ok,
        "pool": {
            "size": stats["pool_size"],
            "available": stats["pool_available"],
            "waiting": stats["requests_waiting"],
        },
    }


_pool = get_pool()

# Validate escrow env (non-fatal: offchain games still work)
from core.escrow import validate_escrow_env
for _warn in validate_escrow_env():
    _log.warning("escrow_env: %s", _warn)

event_store = GameEventStore(_pool)
summary_store = HandSummaryStore(_pool)
stats_store = PlayerStatsStore(_pool)
metadata_store = GameMetadataStore(_pool)
stream_store = StreamStore(_pool)


def _make_recorder(game_id: int) -> GameRecorder:
    return GameRecorder(game_id, event_store, summary_store, stats_store)


manager = GameManager(recorder_factory=_make_recorder, metadata_store=metadata_store)
account_store = AccountStore(_pool)
balance_store = BalanceStore(_pool)
auth_audit = AuthAuditStore(_pool)
escrow_audit = EscrowAuditStore(_pool)

require_auth = make_auth_dependency(lambda: account_store, get_audit=lambda: auth_audit)


# ── Helpers ──────────────────────────────────────────────

def _get_game_or_404(game_id: int) -> tuple[Game, GameConfig]:
    game = manager.get_game(game_id)
    config = manager.get_config(game_id)
    if game is None or config is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game, config


def _recent_actions(game: Game, include_reason: bool = False) -> list[RecentAction]:
    actions = game.recent_actions
    if game.current_hand:
        actions = game.current_hand.actions
    return [_action_to_recent(a, include_reason) for a in actions[-20:]]


def _action_to_recent(a, include_reason: bool = False) -> RecentAction:
    return RecentAction(
        id=a.id, timestamp=a.timestamp,
        player=a.player_name, action=a.action,
        amount=a.amount, comment=a.comment,
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


# ── Game CRUD routes ─────────────────────────────────────

@app.post("/api/games", response_model=CreateGameResponse)
def create_game(req: CreateGameRequest):
    try:
        mode = game_service.infer_mode(req.mode, req.token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def _on_game_over(g: Game, c: GameConfig) -> None:
        settlement_service.settle_offchain_game(g, c, balance_store)
        manager.cleanup_completed()

    game_id, game, config = game_service.create_game(
        manager, req.max_players, req.token, req.buy_in, mode,
        token_decimals=req.token_decimals,
        token_symbol=req.token_symbol,
        on_game_over=_on_game_over,
        action_timeout=req.action_timeout,
        extensions_per_player=req.extensions_per_player,
    )
    return CreateGameResponse(
        game_id=game_id,
        max_players=config.max_players,
        token=config.token,
        buy_in=config.buy_in,
        buy_in_display=config.buy_in_display,
        token_symbol=config.token_symbol,
        mode=config.mode or GameMode.OFFCHAIN,
    )


# ── Game-specific routes ─────────────────────────────────

@app.post("/game/{game_id}/join", response_model=JoinGameResponse)
def join_game(game_id: int, req: JoinGameRequest, account: Account = Depends(require_auth)):
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


@app.get("/game/{game_id}/waiting", response_model=WaitingResponse)
def waiting(game_id: int):
    game, _config = _get_game_or_404(game_id)
    return WaitingResponse(
        started=game.started,
        players=[
            PlayerBrief(id=p.id, name=p.name, chips=p.chips)
            for p in game._players
        ],
        player_count=game.player_count,
    )


@app.post("/game/{game_id}/start", response_model=StartResponse)
def start(game_id: int, account: Account = Depends(require_auth)):
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


# ── Escrow routes ────────────────────────────────────────

@app.get("/game/{game_id}/escrow", response_model=EscrowInfoResponse)
def escrow_info(game_id: int):
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


@app.get("/game/{game_id}/funding", response_model=FundingStatusResponse)
def funding_status(game_id: int):
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


@app.get("/game/{game_id}/settlement", response_model=SettlementResponse)
def settlement(game_id: int):
    game, config = _get_game_or_404(game_id)
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


# ── Game state & action routes ───────────────────────────

@app.get("/game/{game_id}/state", response_model=PlayerStateResponse)
def state(game_id: int, account: Account = Depends(require_auth)):
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


@app.post("/game/{game_id}/resign", response_model=ActionResponse)
def resign(game_id: int, account: Account = Depends(require_auth)):
    game, config = _get_game_or_404(game_id)
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    player = game.get_player_by_name(account.username)
    if player is None:
        raise HTTPException(status_code=404, detail="Not a player in this game")

    result = game.resign(player.id)
    if result == "ok":
        return ActionResponse(success=True, message="Resigned from game")
    else:
        raise HTTPException(status_code=400, detail=result)


@app.post("/game/{game_id}/action", response_model=ActionResponse)
def action(game_id: int, req: ActionRequest, account: Account = Depends(require_auth)):
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
    else:
        raise HTTPException(status_code=400, detail=result)


# ── Spectator ────────────────────────────────────────────

def _build_spectator_response(game: Game, config: GameConfig, **overrides) -> SpectatorResponse:
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
    )
    base.update(overrides)
    return SpectatorResponse(**base)


@app.get("/game/{game_id}/spectator", response_model=SpectatorResponse)
def spectator(game_id: int):
    game, config = _get_game_or_404(game_id)
    game._check_timeout()
    return _build_spectator_response(game, config)


# ── Chat & Timer routes ─────────────────────────────────

@app.post("/game/{game_id}/chat", response_model=ChatResponse)
def chat(game_id: int, req: ChatRequest, account: Account = Depends(require_auth)):
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


@app.post("/game/{game_id}/extend", response_model=ExtendResponse)
def extend(game_id: int, account: Account = Depends(require_auth)):
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


# ── Stream routes ─────────────────────────────────────

@app.post("/game/{game_id}/streams", response_model=CreateStreamResponse)
def create_stream(game_id: int, req: CreateStreamRequest, account: Account = Depends(require_auth)):
    _get_game_or_404(game_id)
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    if len(title) > 100:
        raise HTTPException(status_code=400, detail="Title too long (max 100 chars)")
    try:
        stream = stream_store.create(game_id, account.username, title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CreateStreamResponse(stream_id=stream.id)


@app.post("/stream/{stream_id}/commentate", response_model=CommentateResponse)
def stream_commentate(stream_id: int, req: CommentateRequest, account: Account = Depends(require_auth)):
    stream = stream_store.get(stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Stream not found")
    if stream.host_username != account.username:
        raise HTTPException(status_code=403, detail="Only the stream host can commentate")
    stream_store.update_commentary(stream_id, req.text)
    return CommentateResponse(success=True)


@app.get("/stream/{stream_id}/data", response_model=SpectatorResponse)
def stream_view(stream_id: int):
    stream = stream_store.get(stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Stream not found")
    game = manager.get_game(stream.game_id)
    config = manager.get_config(stream.game_id)
    if game is None or config is None:
        raise HTTPException(status_code=404, detail="Game not found")
    game._check_timeout()
    return _build_spectator_response(
        game, config,
        commentary_text=stream.commentary_text,
        stream_id=stream.id,
        stream_title=stream.title,
        stream_host=stream.host_username,
        stream_created_at=stream.created_at,
    )


@app.get("/game/{game_id}/offchain-settlement", response_model=OffchainSettlementResponse)
def offchain_settlement(game_id: int):
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
