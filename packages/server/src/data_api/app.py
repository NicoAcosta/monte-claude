"""Data API — read-only endpoints over PostgreSQL + static files (port 8000)."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from prometheus_fastapi_instrumentator import Instrumentator

from core.logging_config import configure_logging, RequestContextMiddleware

configure_logging()

_log = logging.getLogger("poker.data_api")

from core.cache import TTLCache
from core.db import get_pool
from core.formatting import format_buy_in
from core.game_metadata_store import GameMetadataStore
from core.game_mode import GameMode
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore
from core.models import (
    GameEventResponse,
    GameHistoryResponse,
    GameListItem,
    GameListResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    PlayerStatsResponse,
    StreamListItem,
    StreamListResponse,
    TokenStatsEntry,
)
from poker.models import (
    HandSummariesResponse,
    HandSummaryResponse,
    RecentHandItem,
    RecentHandsResponse,
)
from core.stream_store import StreamStore


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    _ensure_stores()
    yield


app = FastAPI(title="Monteclaude — Data API", version="0.1.0", lifespan=lifespan)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ── Tier 1: HTTP Cache-Control headers ──────────────────
# Maps path prefixes to max-age seconds.  Checked first-match.
_CACHE_RULES: list[tuple[str, int]] = [
    ("/api/leaderboard", 30),
    ("/api/recent-hands", 15),
    ("/api/stats/", 30),
    ("/api/games/", 5),
    ("/api/games", 3),
    ("/api/streams", 5),
    ("/api/config", 300),
    ("/api/instructions", 120),
    ("/api/play", 120),
]


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        path = request.url.path
        for prefix, max_age in _CACHE_RULES:
            if path.startswith(prefix):
                response.headers["Cache-Control"] = f"public, max-age={max_age}"
                break
        return response


app.add_middleware(RequestContextMiddleware)
app.add_middleware(CacheControlMiddleware)


@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception):
    _log.exception("unhandled_exception path=%s", request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


# ── Tier 2: in-process TTL cache ────────────────────────
_cache = TTLCache()


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


STATIC_DIR = Path(__file__).parent.parent.parent.parent / "frontend"
INSTRUCTIONS_PATH = Path(__file__).parent.parent.parent.parent.parent / "instructions.md"
SKILL_PATH = Path(__file__).parent.parent.parent.parent.parent / ".claude" / "skills" / "play-monteclaude.md"

# Stores are initialised lazily at first request (not at import time) so that
# each uvicorn worker creates its own DB connections after fork().
event_store: GameEventStore | None = None
summary_store: HandSummaryStore | None = None
stats_store: PlayerStatsStore | None = None
metadata_store: GameMetadataStore | None = None
stream_store: StreamStore | None = None


def _ensure_stores() -> None:
    """Create stores on first call — safe to call after fork."""
    global event_store, summary_store, stats_store, metadata_store, stream_store
    if event_store is not None:
        return
    pool = get_pool()
    event_store = GameEventStore(pool)
    summary_store = HandSummaryStore(pool)
    stats_store = PlayerStatsStore(pool)
    metadata_store = GameMetadataStore(pool)
    stream_store = StreamStore(pool)



# API URLs — frontend needs these to reach the correct services
GAME_API_URL = os.environ.get("GAME_API_URL", "")
ACCOUNT_API_URL = os.environ.get("ACCOUNT_API_URL", "")
MONTE_TOKEN_ADDRESS = os.environ.get("MONTE_TOKEN_ADDRESS", "")
BASE_PUBLIC_RPCS = [
    "https://mainnet.base.org",
    "https://base.llamarpc.com",
    "https://base.drpc.org",
    "https://base-rpc.publicnode.com",
]

# ── Default limits for read endpoints ────────────────────
MAX_EVENTS = 200
MAX_HANDS = 100


# ── Config endpoint (tells frontend where other APIs live) ──
@app.get("/api/config")
def get_config():
    return JSONResponse({
        "game_api_url": GAME_API_URL,
        "account_api_url": ACCOUNT_API_URL,
        "monte_token_address": MONTE_TOKEN_ADDRESS,
        "base_rpc_urls": BASE_PUBLIC_RPCS,
    })


# ── Static file routes ───────────────────────────────────

@app.get("/")
def lobby_page():
    return FileResponse(STATIC_DIR / "lobby.html")


@app.get("/watch/{game_id}")
def game_page(game_id: str):
    if not metadata_store.exists(game_id):
        raise HTTPException(status_code=404, detail="Game not found")
    return FileResponse(STATIC_DIR / "spectator.html")


@app.get("/stream/{stream_id}")
def stream_page(stream_id: int):
    stream = stream_store.get(stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Stream not found")
    return FileResponse(STATIC_DIR / "spectator.html")


@app.get("/leaderboard")
def leaderboard_page():
    return FileResponse(STATIC_DIR / "leaderboard.html")


@app.get("/player/{username}")
def player_page(username: str):
    return FileResponse(STATIC_DIR / "player.html")


@app.get("/api/instructions", response_class=PlainTextResponse)
def instructions():
    if not INSTRUCTIONS_PATH.is_file():
        raise HTTPException(status_code=404, detail="Instructions file not found")
    return PlainTextResponse(INSTRUCTIONS_PATH.read_text())


@app.get("/api/play", response_class=PlainTextResponse)
def play_skill():
    if not SKILL_PATH.is_file():
        raise HTTPException(status_code=404, detail="Skill file not found")
    return PlainTextResponse(SKILL_PATH.read_text())


# ── Lobby ────────────────────────────────────────────────

@app.get("/api/games", response_model=GameListResponse)
def list_games():
    cached = _cache.get("games")
    if cached is not None:
        return cached
    rows = metadata_store.list_all()
    result = GameListResponse(
        games=[
            GameListItem(
                id=r.game_id,
                game_type=r.game_type,
                player_count=r.player_count,
                player_names=r.player_names,
                started=r.started,
                game_over=r.game_over,
                winner=r.winner,
                hand_number=r.hand_number,
                max_players=r.max_players,
                token=r.token,
                buy_in=r.buy_in,
                buy_in_display=format_buy_in(r.buy_in, r.token_decimals, r.token_symbol, r.mode),
                token_symbol=r.token_symbol,
                funded=r.funded,
                mode=r.mode or GameMode.OFFCHAIN,
            )
            for r in rows
        ]
    )
    _cache.set("games", result, ttl=3)
    return result


# ── History routes ──────────────────────────────────────

# Keys stripped from raw event JSON — seeds are available via summary endpoints.
_EVENT_REDACTED_KEYS = frozenset({"seed_hex"})


def _sanitize_event_data(raw: str) -> str:
    """Remove sensitive fields from event JSON before returning to clients."""
    parsed = json.loads(raw)
    if any(k in parsed for k in _EVENT_REDACTED_KEYS):
        for k in _EVENT_REDACTED_KEYS:
            parsed.pop(k, None)
        return json.dumps(parsed, separators=(",", ":"))
    return raw


@app.get("/api/games/{game_id}/history", response_model=GameHistoryResponse)
def game_history(game_id: str, limit: int = Query(default=MAX_EVENTS, ge=1, le=MAX_EVENTS)):
    if not metadata_store.exists(game_id):
        raise HTTPException(status_code=404, detail="Game not found")
    events = event_store.get_by_game(game_id)
    # Apply limit: return only the most recent N events
    events = events[-limit:]
    return GameHistoryResponse(
        game_id=game_id,
        events=[
            GameEventResponse(
                game_id=e.game_id,
                event_type=e.event_type,
                timestamp=e.timestamp,
                hand_number=e.hand_number,
                data=_sanitize_event_data(e.data),
                sequence=e.sequence,
            )
            for e in events
        ],
    )


@app.get("/api/games/{game_id}/hands", response_model=HandSummariesResponse)
def hand_summaries(game_id: str, limit: int = Query(default=MAX_HANDS, ge=1, le=MAX_HANDS)):
    if not metadata_store.exists(game_id):
        raise HTTPException(status_code=404, detail="Game not found")
    summaries = summary_store.get_by_game(game_id)
    # Apply limit: return only the most recent N hands
    summaries = summaries[-limit:]
    return HandSummariesResponse(
        game_id=game_id,
        hands=[
            HandSummaryResponse(
                game_id=s.game_id,
                hand_number=s.hand_number,
                dealer_id=s.dealer_id,
                player_ids=list(s.player_ids),
                winner_ids=list(s.winner_ids),
                pot=s.pot,
                community_cards=s.community_cards,
                timestamp=s.timestamp,
                winner_names=list(s.winner_names),
                winning_cards=json.loads(s.winning_cards) if isinstance(s.winning_cards, str) else s.winning_cards,
                result_type=s.result_type,
                token_symbol=s.token_symbol,
                seed_hex=s.seed_hex,
                seed_commitment=s.seed_commitment,
            )
            for s in summaries
        ],
    )


@app.get("/api/stats/{username}", response_model=PlayerStatsResponse)
def player_stats(username: str):
    cache_key = f"stats:{username}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    stats = stats_store.get(username)
    if stats is None:
        raise HTTPException(status_code=404, detail="Player not found")
    token_stats = stats_store.get_token_stats(username)
    result = PlayerStatsResponse(
        username=stats.username,
        games_played=stats.games_played,
        hands_played=stats.hands_played,
        hands_won=stats.hands_won,
        total_winnings=stats.total_winnings,
        biggest_pot_won=stats.biggest_pot_won,
        token_stats=[TokenStatsEntry(**ts) for ts in token_stats],
    )
    _cache.set(cache_key, result, ttl=30)
    return result


MAX_LEADERBOARD = 50
MAX_RECENT_HANDS = 20


@app.get("/api/leaderboard", response_model=LeaderboardResponse)
def leaderboard(
    limit: int = Query(default=MAX_LEADERBOARD, ge=1, le=MAX_LEADERBOARD),
    offset: int = Query(default=0, ge=0),
):
    cache_key = f"leaderboard:{limit}:{offset}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    total = stats_store.count_all()
    all_stats = stats_store.get_all(limit=limit, offset=offset)
    all_token_stats = stats_store.get_all_token_stats()
    result = LeaderboardResponse(
        total=total,
        players=[
            LeaderboardEntry(
                rank=offset + i + 1,
                username=s.username,
                games_played=s.games_played,
                hands_won=s.hands_won,
                win_rate=round(s.hands_won / s.hands_played * 100, 1) if s.hands_played > 0 else 0.0,
                total_winnings=s.total_winnings,
                biggest_pot_won=s.biggest_pot_won,
                token_stats=[TokenStatsEntry(**ts) for ts in all_token_stats.get(s.username, [])],
            )
            for i, s in enumerate(all_stats)
        ],
    )
    _cache.set(cache_key, result, ttl=15)
    return result


@app.get("/api/recent-hands", response_model=RecentHandsResponse)
def recent_hands(
    limit: int = Query(default=MAX_RECENT_HANDS, ge=1, le=MAX_RECENT_HANDS),
    offset: int = Query(default=0, ge=0),
):
    cache_key = f"recent-hands:{limit}:{offset}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    total = summary_store.count_all()
    hands = summary_store.get_recent(limit=limit, offset=offset)
    result = RecentHandsResponse(
        total=total,
        hands=[
            RecentHandItem(
                game_id=h.game_id,
                hand_number=h.hand_number,
                winner_ids=list(h.winner_ids),
                winner_names=list(h.winner_names),
                pot=h.pot,
                timestamp=h.timestamp,
                winning_cards=json.loads(h.winning_cards) if isinstance(h.winning_cards, str) else h.winning_cards,
                result_type=h.result_type,
                token_symbol=h.token_symbol,
                seed_hex=h.seed_hex,
                seed_commitment=h.seed_commitment,
            )
            for h in hands
        ],
    )
    _cache.set(cache_key, result, ttl=10)
    return result


# ── Stream routes ────────────────────────────────────────

@app.get("/api/streams", response_model=StreamListResponse)
def list_all_streams():
    summaries = stream_store.list_all()
    return StreamListResponse(
        streams=[
            StreamListItem(id=s.id, game_id=s.game_id, host=s.host_username, title=s.title)
            for s in summaries
        ]
    )


@app.get("/api/games/{game_id}/streams", response_model=StreamListResponse)
def list_streams_for_game(game_id: str):
    if not metadata_store.exists(game_id):
        raise HTTPException(status_code=404, detail="Game not found")
    summaries = stream_store.list_for_game(game_id)
    return StreamListResponse(
        streams=[
            StreamListItem(id=s.id, game_id=s.game_id, host=s.host_username, title=s.title)
            for s in summaries
        ]
    )
