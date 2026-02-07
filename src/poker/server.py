from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse

from poker.account_store import Account, AccountStore
from poker.auth import make_auth_dependency
from poker.game import Game
from poker.game_manager import GameManager
from poker.game_recorder import GameRecorder
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore
from poker.models import (
    AccountRegisterRequest,
    AccountRegisterResponse,
    ActionRequest,
    ActionResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    CommentateRequest,
    CommentateResponse,
    CreateGameResponse,
    ExtendResponse,
    GameEventResponse,
    GameHistoryResponse,
    GameListItem,
    GameListResponse,
    HandSummariesResponse,
    HandSummaryResponse,
    JoinGameResponse,
    PlayerBrief,
    PlayerComment,
    PlayerPublicState,
    PlayerStateResponse,
    PlayerStatsResponse,
    RecentAction,
    SidePotInfo,
    SpectatorPlayerState,
    SpectatorResponse,
    StartResponse,
    TimerInfo,
    WaitingResponse,
)

app = FastAPI(title="Claude Poker", version="0.1.0")

STATIC_DIR = Path(__file__).parent.parent.parent / "static"
DATA_DIR = Path(__file__).parent.parent.parent / "data"

event_store = GameEventStore(DATA_DIR / "events.csv")
summary_store = HandSummaryStore(DATA_DIR / "hand_summaries.csv")
stats_store = PlayerStatsStore(DATA_DIR / "player_stats.csv")


def _make_recorder(game_id: int) -> GameRecorder:
    return GameRecorder(game_id, event_store, summary_store, stats_store)


manager = GameManager(recorder_factory=_make_recorder)
account_store = AccountStore(DATA_DIR / "accounts.csv")

require_auth = make_auth_dependency(lambda: account_store)


def _get_game_or_404(game_id: int) -> Game:
    game = manager.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


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
    """Extract the latest comment per player from current hand actions."""
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


# ── Account routes ───────────────────────────────────────

@app.post("/api/register", response_model=AccountRegisterResponse)
def register_account(req: AccountRegisterRequest):
    try:
        api_key = account_store.create_account(req.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AccountRegisterResponse(api_key=api_key, username=req.username)


# ── Lobby routes ─────────────────────────────────────────

@app.get("/")
def lobby_page():
    return FileResponse(STATIC_DIR / "lobby.html")


@app.get("/api/games", response_model=GameListResponse)
def list_games():
    summaries = manager.list_games()
    return GameListResponse(
        games=[
            GameListItem(
                id=s.id,
                player_count=s.player_count,
                player_names=list(s.player_names),
                started=s.started,
                game_over=s.game_over,
                winner=s.winner,
                hand_number=s.hand_number,
            )
            for s in summaries
        ]
    )


@app.post("/api/games", response_model=CreateGameResponse)
def create_game():
    game_id, _ = manager.create_game()
    return CreateGameResponse(game_id=game_id)


# ── Game-specific routes ─────────────────────────────────

@app.get("/game/{game_id}")
def game_page(game_id: int):
    _get_game_or_404(game_id)
    return FileResponse(STATIC_DIR / "spectator.html")


@app.post("/game/{game_id}/join", response_model=JoinGameResponse)
def join_game(game_id: int, account: Account = Depends(require_auth)):
    game = _get_game_or_404(game_id)
    try:
        p = game.register(account.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    recorder = manager.get_recorder(game_id)
    if recorder:
        recorder.on_event("player_joined", {
            "player_name": p.name,
            "player_id": p.id,
        })

    return JoinGameResponse(player_id=p.id, name=p.name)


@app.get("/game/{game_id}/waiting", response_model=WaitingResponse)
def waiting(game_id: int):
    game = _get_game_or_404(game_id)
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
    game = _get_game_or_404(game_id)
    # Must be a player in the game to start it
    if game.get_player_by_name(account.username) is None:
        raise HTTPException(status_code=403, detail="Not a player in this game")
    try:
        hand_num = game.start()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    recorder = manager.get_recorder(game_id)
    if recorder:
        recorder.on_event("game_started", {
            "player_count": game.player_count,
            "player_names": [p.name for p in game._players],
        })

    return StartResponse(message="Game started", hand_number=hand_num)


@app.post("/game/{game_id}/commentate", response_model=CommentateResponse)
def commentate(game_id: int, req: CommentateRequest, account: Account = Depends(require_auth)):
    game = _get_game_or_404(game_id)
    game.commentary_text = req.text
    return CommentateResponse(success=True)


@app.get("/game/{game_id}/state/{player_id}", response_model=PlayerStateResponse)
def state(game_id: int, player_id: int):
    game = _get_game_or_404(game_id)
    rp = game.get_player(player_id)
    if rp is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    game._check_timeout()

    hand = game.current_hand

    if hand is None:
        # Game over or between hands
        return PlayerStateResponse(
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
            commentary_text=game.commentary_text,
            chat_log=_chat_log(game),
        )

    # Find this player in the hand
    hand_player = hand._get_player(player_id)
    your_cards = [str(c) for c in hand_player.hole_cards] if hand_player else []
    your_chips = hand_player.chips if hand_player else rp.chips
    your_bet = hand_player.current_bet if hand_player else 0

    current_turn_id = hand.current_player.id if hand.current_player else None

    side_pots = hand.get_side_pots_info()

    return PlayerStateResponse(
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
            )
            for p in hand.players
        ],
        game_over=game.game_over,
        winner=game.winner,
        recent_actions=_recent_actions(game),
        player_comments=_player_comments(game),
        commentary_text=game.commentary_text,
        chat_log=_chat_log(game),
        timer=_timer_info(game, player_id),
    )


@app.post("/game/{game_id}/action", response_model=ActionResponse)
def action(game_id: int, req: ActionRequest, account: Account = Depends(require_auth)):
    game = _get_game_or_404(game_id)
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    game._check_timeout()

    player = game.get_player_by_name(account.username)
    if player is None:
        raise HTTPException(status_code=404, detail="Not a player in this game")

    if req.reason is not None and len(req.reason) > 500:
        raise HTTPException(status_code=400, detail="Reason too long (max 500 chars)")

    result = game.do_action(player.id, req.action, req.amount, comment=req.comment, reason=req.reason)
    if result == "ok":
        return ActionResponse(success=True, message="Action accepted")
    else:
        raise HTTPException(status_code=400, detail=result)


@app.get("/game/{game_id}/spectator", response_model=SpectatorResponse)
def spectator(game_id: int):
    game = _get_game_or_404(game_id)
    game._check_timeout()
    prev = game.previous_hand

    # No previous hand yet (hand 1 in progress or game not started)
    if prev is None:
        return SpectatorResponse(
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
                )
                for p in game._players
            ],
            game_over=game.game_over,
            winner=game.winner,
            recent_actions=[],
            started=game.started,
            commentary_text=game.commentary_text,
            chat_log=_chat_log(game),
            timer=_timer_info(game),
        )

    # Serve the previous hand's complete state
    side_pots = prev.get_side_pots_info()

    return SpectatorResponse(
        hand_number=game.hand_number - 1,
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
            )
            for p in prev.players
        ],
        game_over=game.game_over,
        winner=game.winner,
        recent_actions=[_action_to_recent(a, include_reason=True) for a in prev.actions],
        started=game.started,
        commentary_text=game.commentary_text,
        chat_log=_chat_log(game),
        timer=_timer_info(game),
    )


# ── Chat & Timer routes ─────────────────────────────────

@app.post("/game/{game_id}/chat", response_model=ChatResponse)
def chat(game_id: int, req: ChatRequest, account: Account = Depends(require_auth)):
    game = _get_game_or_404(game_id)
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
    game = _get_game_or_404(game_id)
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    player = game.get_player_by_name(account.username)
    if player is None:
        raise HTTPException(status_code=403, detail="Not a player in this game")

    game._check_timeout()

    result = game.use_extension(player.id)
    if result is None:
        raise HTTPException(status_code=400, detail="Cannot extend (not your turn or no extensions left)")

    new_deadline, remaining = result
    return ExtendResponse(success=True, new_deadline=new_deadline, extensions_remaining=remaining)


# ── History routes ──────────────────────────────────────

@app.get("/api/games/{game_id}/history", response_model=GameHistoryResponse)
def game_history(game_id: int):
    _get_game_or_404(game_id)
    events = event_store.get_by_game(game_id)
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
def hand_summaries(game_id: int):
    _get_game_or_404(game_id)
    summaries = summary_store.get_by_game(game_id)
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
