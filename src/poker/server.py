from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse


from poker.game import Game
from poker.models import (
    ActionRequest,
    ActionResponse,
    CommentateRequest,
    CommentateResponse,
    PlayerBrief,
    PlayerComment,
    PlayerPublicState,
    PlayerStateResponse,
    RecentAction,
    RegisterRequest,
    RegisterResponse,
    SidePotInfo,
    SpectatorPlayerState,
    SpectatorResponse,
    StartResponse,
    WaitingResponse,
)

app = FastAPI(title="Claude Poker", version="0.1.0")

STATIC_DIR = Path(__file__).parent.parent.parent / "static"

game = Game()


def _recent_actions() -> list[RecentAction]:
    actions = game.recent_actions
    if game.current_hand:
        actions = game.current_hand.actions
    return [_action_to_recent(a) for a in actions[-20:]]


def _action_to_recent(a) -> RecentAction:
    return RecentAction(
        id=a.id, timestamp=a.timestamp,
        player=a.player_name, action=a.action,
        amount=a.amount, comment=a.comment,
    )


def _player_comments() -> list[PlayerComment]:
    """Extract the latest comment per player from current hand actions."""
    actions = game.current_hand.actions if game.current_hand else game.recent_actions
    latest: dict[str, str] = {}
    for a in actions:
        if a.comment:
            latest[a.player_name] = a.comment
    return [PlayerComment(player=name, comment=text) for name, text in latest.items()]


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/register", response_model=RegisterResponse)
def register(req: RegisterRequest):
    try:
        p = game.register(req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RegisterResponse(player_id=p.id, name=p.name)


@app.get("/waiting", response_model=WaitingResponse)
def waiting():
    return WaitingResponse(
        started=game.started,
        players=[
            PlayerBrief(id=p.id, name=p.name, chips=p.chips)
            for p in game._players
        ],
        player_count=game.player_count,
    )


@app.post("/start", response_model=StartResponse)
def start():
    try:
        hand_num = game.start()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StartResponse(message="Game started", hand_number=hand_num)


@app.post("/commentate", response_model=CommentateResponse)
def commentate(req: CommentateRequest):
    game.commentary_text = req.text
    return CommentateResponse(success=True)


@app.get("/state/{player_id}", response_model=PlayerStateResponse)
def state(player_id: int):
    rp = game.get_player(player_id)
    if rp is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

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
            recent_actions=_recent_actions(),
            player_comments=_player_comments(),
            commentary_text=game.commentary_text,
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
        recent_actions=_recent_actions(),
        player_comments=_player_comments(),
        commentary_text=game.commentary_text,
    )


@app.post("/action", response_model=ActionResponse)
def action(req: ActionRequest):
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    result = game.do_action(req.player_id, req.action, req.amount, comment=req.comment)
    if result == "ok":
        return ActionResponse(success=True, message="Action accepted")
    else:
        raise HTTPException(status_code=400, detail=result)


@app.get("/spectator", response_model=SpectatorResponse)
def spectator():
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
        recent_actions=[_action_to_recent(a) for a in prev.actions],
        started=game.started,
        commentary_text=game.commentary_text,
    )
