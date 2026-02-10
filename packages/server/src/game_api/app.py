"""Game API — thin shell: middleware, health, streams, router inclusion (port 8001)."""

from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from prometheus_fastapi_instrumentator import Instrumentator

from core.logging_config import configure_logging, RequestContextMiddleware

configure_logging()

_log = logging.getLogger("poker.game_api")

if not os.environ.get("SERVER_PRIVATE_KEY"):
    raise SystemExit("FATAL: SERVER_PRIVATE_KEY env var is required")

from core.account_store import Account, AccountStore
from core.audit import AuthAuditStore, EscrowAuditStore
from core.auth import make_auth_dependency
from core.balance_store import BalanceStore
from core.db import get_pool
from core.game_manager import GameManager
from core.game_metadata_store import GameMetadataStore
from core.game_recorder import GameRecorder
from core.history_store import GameEventStore, PlayerStatsStore
from core.models import (
    CommentateRequest,
    CommentateResponse,
    CreateStreamRequest,
    CreateStreamResponse,
    StreamListItem,
    StreamListResponse,
)
from core.stream_store import StreamStore
from core.round_summary_store import RoundSummaryStore
from dice.game import DiceGame
from dice.recorder import make_dice_materializer
from dice.router import router as dice_router, configure as configure_dice_router
from poker.game import Game
from poker.history_store import HandSummaryStore
from poker.recorder import make_poker_materializer
from poker.router import router as poker_router, configure as configure_poker_router
from poker.router import _build_spectator_response as _build_poker_spectator_response
from dice.router import _build_spectator_response as _build_dice_spectator_response

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


@app.get("/attestation")
def attestation(nonce: str | None = None):
    """Return NSM attestation document with server Ethereum address bound as user_data."""
    from core.attestation import NsmError, get_attestation
    from core.escrow import get_server_address
    from core.models import AttestationResponse

    server_address = get_server_address()
    if not server_address:
        raise HTTPException(status_code=500, detail="Server identity not configured")

    # Validate and decode optional nonce
    nonce_bytes: bytes | None = None
    if nonce is not None:
        try:
            nonce_bytes = bytes.fromhex(nonce)
        except ValueError:
            raise HTTPException(status_code=400, detail="Nonce must be a hex string")
        if len(nonce_bytes) > 512:
            raise HTTPException(status_code=400, detail="Nonce too long (max 512 bytes)")

    # Embed server Ethereum address as user_data (20 bytes)
    address_bytes = bytes.fromhex(server_address[2:])  # strip 0x prefix

    try:
        result = get_attestation(user_data=address_bytes, nonce=nonce_bytes)
    except NsmError:
        # Dev mode — return synthetic attestation with deterministic PCR-0
        import base64 as _b64
        import time as _time

        dev_pcr0 = b"\x00" * 48  # all-zero PCR-0 signals dev mode
        return AttestationResponse(
            document=_b64.b64encode(b"DEV_MODE_NO_NSM").decode(),
            module_id="dev-mode",
            timestamp=int(_time.time() * 1000),
            digest="SHA384",
            pcrs={
                "0": dev_pcr0.hex(),
                "1": (b"\x00" * 48).hex(),
                "2": (b"\x00" * 48).hex(),
            },
            user_data=address_bytes.hex(),
            nonce=nonce_bytes.hex() if nonce_bytes else None,
            server_address=server_address,
        )

    import base64

    payload = result.payload
    # Only include PCR 0-2 in parsed response
    pcrs_hex = {
        str(k): v.hex()
        for k, v in payload.pcrs.items()
        if k in (0, 1, 2)
    }

    return AttestationResponse(
        document=base64.b64encode(result.raw_document).decode(),
        module_id=payload.module_id,
        timestamp=payload.timestamp,
        digest=payload.digest,
        pcrs=pcrs_hex,
        user_data=payload.user_data.hex() if payload.user_data else None,
        nonce=payload.nonce.hex() if payload.nonce else None,
        server_address=server_address,
    )


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


# ── Store & factory initialisation ────────────────────────

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
round_summary_store = RoundSummaryStore(_pool)

_poker_materializer = make_poker_materializer(summary_store)
_dice_materializer = make_dice_materializer(round_summary_store)

_materializers = {
    "poker": _poker_materializer,
    "dice": _dice_materializer,
}


def _make_recorder(game_id: int, game_type: str) -> GameRecorder:
    materializer = _materializers.get(game_type)
    return GameRecorder(game_id, event_store, stats_store, summary_materializer=materializer)


manager = GameManager(recorder_factory=_make_recorder, metadata_store=metadata_store)
manager.register_game_type("poker", Game)
manager.register_game_type("dice", DiceGame)

# Apply env-based game type restrictions.
# ENABLED_GAME_TYPES="poker,dice" → only those types accept new games.
# Unset → all registered types are enabled (the default).
_enabled_csv = os.environ.get("ENABLED_GAME_TYPES")
if _enabled_csv is not None:
    _allowed = {t.strip().lower() for t in _enabled_csv.split(",") if t.strip()}
    for _gt in list(manager.enabled_game_types):
        if _gt not in _allowed:
            manager.disable_game_type(_gt)
            _log.info("game_type_disabled type=%s (not in ENABLED_GAME_TYPES)", _gt)

account_store = AccountStore(_pool)
balance_store = BalanceStore(_pool)
auth_audit = AuthAuditStore(_pool)
escrow_audit = EscrowAuditStore(_pool)

require_auth = make_auth_dependency(lambda: account_store, get_audit=lambda: auth_audit)

# Wire up the poker router with shared stores
configure_poker_router(
    mgr=manager,
    bal=balance_store,
    acc=account_store,
    meta=metadata_store,
    esc_audit=escrow_audit,
    auth_dep=require_auth,
)

app.include_router(poker_router, prefix="/game/poker")

# Wire up the dice router with shared stores
configure_dice_router(
    mgr=manager,
    bal=balance_store,
    acc=account_store,
    meta=metadata_store,
    auth_dep=require_auth,
)

app.include_router(dice_router, prefix="/game/dice")


# ── Stream routes (game-type agnostic) ────────────────────

@app.post("/game/{game_id}/streams", response_model=CreateStreamResponse)
def create_stream(game_id: int, req: CreateStreamRequest, account: Account = Depends(require_auth)):
    game = manager.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
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


def _build_spectator_for_game(game, config, **overrides):
    """Dispatch to the correct spectator response builder based on game type."""
    if game.game_type == "dice":
        return _build_dice_spectator_response(game, config, **overrides)
    return _build_poker_spectator_response(game, config, **overrides)


@app.get("/stream/{stream_id}/data")
def stream_view(stream_id: int):
    stream = stream_store.get(stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Stream not found")
    game = manager.get_game(stream.game_id)
    config = manager.get_config(stream.game_id)
    if game is None or config is None:
        raise HTTPException(status_code=404, detail="Game not found")
    game._check_timeout()
    return _build_spectator_for_game(
        game, config,
        commentary_text=stream.commentary_text,
        stream_id=stream.id,
        stream_title=stream.title,
        stream_host=stream.host_username,
        stream_created_at=stream.created_at,
    )


@app.get("/game/{game_id}/spectator")
def game_spectator_compat(game_id: int):
    """Compat route: dispatches to the correct game-type spectator."""
    game = manager.get_game(game_id)
    config = manager.get_config(game_id)
    if game is None or config is None:
        raise HTTPException(status_code=404, detail="Game not found")
    game._check_timeout()
    return _build_spectator_for_game(game, config)
