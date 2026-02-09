"""Data API — read-only endpoints over PostgreSQL + static files (port 8000)."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

from poker.account_store import Account, AccountStore
from poker.auth import make_auth_dependency
from poker.balance_store import BalanceStore
from poker.db import get_pool
from poker.formatting import format_buy_in
from poker.game_metadata_store import GameMetadataStore
from poker.game_mode import GameMode
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore
from poker.models import (
    BalanceResponse,
    GameEventResponse,
    GameHistoryResponse,
    GameListItem,
    GameListResponse,
    HandSummariesResponse,
    HandSummaryResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    PlayerStatsResponse,
    RecentHandItem,
    RecentHandsResponse,
    StreamListItem,
    StreamListResponse,
)
from poker.stream_store import StreamStore

app = FastAPI(title="Monteclaude — Data API", version="0.1.0")

STATIC_DIR = Path(__file__).parent.parent.parent.parent / "frontend"
INSTRUCTIONS_PATH = Path(__file__).parent.parent.parent.parent.parent / "instructions.md"

_pool = get_pool()

event_store = GameEventStore(_pool)
summary_store = HandSummaryStore(_pool)
stats_store = PlayerStatsStore(_pool)
metadata_store = GameMetadataStore(_pool)
account_store = AccountStore(_pool)
balance_store = BalanceStore(_pool)
stream_store = StreamStore(_pool)

require_auth = make_auth_dependency(lambda: account_store)

# ── Default limits for read endpoints ────────────────────
MAX_EVENTS = 200
MAX_HANDS = 100


# ── Static file routes ───────────────────────────────────

@app.get("/")
def lobby_page():
    return FileResponse(STATIC_DIR / "lobby.html")


@app.get("/game/{game_id}")
def game_page(game_id: int):
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


# ── Lobby ────────────────────────────────────────────────

@app.get("/api/games", response_model=GameListResponse)
def list_games():
    rows = metadata_store.list_all()
    return GameListResponse(
        games=[
            GameListItem(
                id=r.game_id,
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


# ── History routes ──────────────────────────────────────

@app.get("/api/games/{game_id}/history", response_model=GameHistoryResponse)
def game_history(game_id: int, limit: int = Query(default=MAX_EVENTS, ge=1, le=MAX_EVENTS)):
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
                data=e.data,
                sequence=e.sequence,
            )
            for e in events
        ],
    )


@app.get("/api/games/{game_id}/hands", response_model=HandSummariesResponse)
def hand_summaries(game_id: int, limit: int = Query(default=MAX_HANDS, ge=1, le=MAX_HANDS)):
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
            )
            for s in summaries
        ],
    )


@app.get("/api/stats/{username}", response_model=PlayerStatsResponse)
def player_stats(username: str):
    stats = stats_store.get(username)
    if stats is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return PlayerStatsResponse(
        username=stats.username,
        games_played=stats.games_played,
        hands_played=stats.hands_played,
        hands_won=stats.hands_won,
        total_winnings=stats.total_winnings,
        biggest_pot_won=stats.biggest_pot_won,
    )


MAX_LEADERBOARD = 50
MAX_RECENT_HANDS = 20


@app.get("/api/leaderboard", response_model=LeaderboardResponse)
def leaderboard(limit: int = Query(default=MAX_LEADERBOARD, ge=1, le=MAX_LEADERBOARD)):
    all_stats = stats_store.get_all(limit=limit)
    return LeaderboardResponse(
        players=[
            LeaderboardEntry(
                rank=i + 1,
                username=s.username,
                games_played=s.games_played,
                hands_won=s.hands_won,
                win_rate=round(s.hands_won / s.hands_played * 100, 1) if s.hands_played > 0 else 0.0,
                total_winnings=s.total_winnings,
                biggest_pot_won=s.biggest_pot_won,
            )
            for i, s in enumerate(all_stats)
        ]
    )


@app.get("/api/recent-hands", response_model=RecentHandsResponse)
def recent_hands(limit: int = Query(default=MAX_RECENT_HANDS, ge=1, le=MAX_RECENT_HANDS)):
    hands = summary_store.get_recent(limit=limit)
    return RecentHandsResponse(
        hands=[
            RecentHandItem(
                game_id=h.game_id,
                hand_number=h.hand_number,
                winner_ids=list(h.winner_ids),
                pot=h.pot,
                timestamp=h.timestamp,
            )
            for h in hands
        ]
    )


# ── Balance route ────────────────────────────────────────

@app.get("/api/balance", response_model=BalanceResponse)
def get_balance(account: Account = Depends(require_auth)):
    bal = balance_store.get(account.username)
    return BalanceResponse(username=account.username, balance=bal.amount)


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


@app.get("/game/{game_id}/streams", response_model=StreamListResponse)
def list_streams_for_game(game_id: int):
    if not metadata_store.exists(game_id):
        raise HTTPException(status_code=404, detail="Game not found")
    summaries = stream_store.list_for_game(game_id)
    return StreamListResponse(
        streams=[
            StreamListItem(id=s.id, game_id=s.game_id, host=s.host_username, title=s.title)
            for s in summaries
        ]
    )
