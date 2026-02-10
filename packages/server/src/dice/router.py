"""Dice game router — all dice-specific HTTP routes.

Mounted with prefix /dice by game_api/app.py.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from core.account_store import Account, AccountStore
from core.balance_store import BalanceStore
from core import game_service, settlement_service
from core.game_config import GameConfig
from core.game_manager import GameManager
from core.game_metadata_store import GameMetadataStore
from core.game_mode import GameMode
from core.models import (
    ActionRequest,
    ActionResponse,
    ChatRequest,
    ChatResponse,
    CreateGameRequest,
    CreateGameResponse,
    ExtendResponse,
    JoinGameRequest,
    JoinGameResponse,
    OffchainPayout,
    OffchainSettlementResponse,
    PlayerBrief,
    StartResponse,
    WaitingResponse,
)
from core.state_builders import build_dice_player_state, build_dice_spectator_state
from dice.game import DiceGame
from dice.models import (
    DiceSpectatorResponse,
    DiceStateResponse,
)

_log = logging.getLogger("dice.router")

router = APIRouter()

# ── Dependency injection ──────────────────────────────────────────

manager: GameManager | None = None
balance_store: BalanceStore | None = None
account_store: AccountStore | None = None
metadata_store: GameMetadataStore | None = None
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
    auth_dep: Callable[..., Account],
) -> None:
    global manager, balance_store, account_store, metadata_store, _auth_callable
    manager = mgr
    balance_store = bal
    account_store = acc
    metadata_store = meta
    _auth_callable = auth_dep


# ── Helpers ───────────────────────────────────────────────────────


def _get_game_or_404(game_id: str) -> tuple[DiceGame, GameConfig]:
    assert manager is not None
    game = manager.get_game(game_id)
    config = manager.get_config(game_id)
    if game is None or config is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.game_type != "dice":
        raise HTTPException(status_code=404, detail="Game not found")
    return game, config  # type: ignore[return-value]


# ── Game CRUD ─────────────────────────────────────────────────────


@router.post("/games", response_model=CreateGameResponse)
def create_game(req: CreateGameRequest) -> CreateGameResponse:
    assert manager is not None and balance_store is not None

    try:
        mode = game_service.validate_mode(req.mode, req.token, game_type="dice")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def _on_game_over(g: DiceGame, c: GameConfig) -> None:
        settlement_service.settle_offchain_game(g, c, balance_store)
        manager.cleanup_completed()

    try:
        game_id, game, config = game_service.create_game(
            manager, req.max_players, req.token, req.buy_in, mode,
            game_type="dice",
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
        game_type="dice",
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
    game, _ = _get_game_or_404(game_id)
    return WaitingResponse(
        started=game.started,
        players=[
            PlayerBrief(id=p.id, name=p.name, chips=p.chips)
            for p in game.players
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
        round_num = game_service.start_game(
            game=game,
            config=config,
            recorder=manager.get_recorder(game_id),
            metadata_store=metadata_store,
            game_id=game_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StartResponse(message="Game started", hand_number=round_num)


# ── State & Action ────────────────────────────────────────────────


@router.get("/{game_id}/state", response_model=DiceStateResponse)
def state(game_id: str, account: Account = Depends(_require_auth)):
    game, config = _get_game_or_404(game_id)
    rp = game.get_player_by_name(account.username)
    if rp is None:
        raise HTTPException(status_code=403, detail="Not a player in this game")
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    game._check_timeout()

    return build_dice_player_state(game, config, rp.id)


@router.post("/{game_id}/action", response_model=ActionResponse)
def action(game_id: str, req: ActionRequest, account: Account = Depends(_require_auth)):
    game, _ = _get_game_or_404(game_id)
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

    result = game.do_action(player.id, req.action, req.amount, comment=req.comment, reason=req.reason)
    if result == "ok":
        return ActionResponse(success=True, message="Action accepted")
    raise HTTPException(status_code=400, detail=result)


@router.post("/{game_id}/resign", response_model=ActionResponse)
def resign(game_id: str, account: Account = Depends(_require_auth)):
    game, _ = _get_game_or_404(game_id)
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


@router.get("/{game_id}/spectator", response_model=DiceSpectatorResponse)
def spectator(game_id: str) -> DiceSpectatorResponse:
    game, config = _get_game_or_404(game_id)
    game._check_timeout()
    return build_dice_spectator_state(game, config)


# ── Chat & Timer ──────────────────────────────────────────────────


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
