from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse

from poker.account_store import Account, AccountStore
from poker.auth import make_auth_dependency
from poker.balance_store import BalanceStore
from poker.game import Game
from poker.game_mode import GameMode
from poker.game_manager import GameManager
from poker.game_recorder import GameRecorder
from poker.history_store import GameEventStore, HandSummaryStore, PlayerStatsStore
from poker.models import (
    AccountRegisterRequest,
    AccountRegisterResponse,
    ActionRequest,
    ActionResponse,
    BalanceResponse,
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
    FaucetResponse,
    FundingStatusResponse,
    GameEventResponse,
    GameHistoryResponse,
    GameListItem,
    GameListResponse,
    HandSummariesResponse,
    HandSummaryResponse,
    JoinGameRequest,
    JoinGameResponse,
    OffchainPayout,
    OffchainSettlementResponse,
    PayoutEntry,
    PlayerBrief,
    PlayerComment,
    PlayerPublicState,
    PlayerStateResponse,
    PlayerStatsResponse,
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
from poker.stream_manager import StreamManager

app = FastAPI(title="Claude Poker", version="0.1.0")

STATIC_DIR = Path(__file__).parent.parent.parent.parent / "frontend"
DATA_DIR = Path(__file__).parent.parent.parent / "data"

event_store = GameEventStore(DATA_DIR / "events.csv")
summary_store = HandSummaryStore(DATA_DIR / "hand_summaries.csv")
stats_store = PlayerStatsStore(DATA_DIR / "player_stats.csv")


def _make_recorder(game_id: int) -> GameRecorder:
    return GameRecorder(game_id, event_store, summary_store, stats_store)


manager = GameManager(recorder_factory=_make_recorder)
account_store = AccountStore(DATA_DIR / "accounts.csv")
balance_store = BalanceStore(DATA_DIR / "balances.csv")
stream_manager = StreamManager()

FAUCET_AMOUNT = 10_000

require_auth = make_auth_dependency(lambda: account_store)


def _settle_offchain_game(game: Game) -> None:
    """Compute and credit offchain payouts when a game ends."""
    if game.mode != GameMode.OFFCHAIN or game.buy_in <= 0:
        return
    if game.offchain_settlement is not None:
        return  # already settled

    from poker.escrow import compute_payouts
    from poker.game import STARTING_CHIPS

    player_chips: dict[str, int] = {p.name: p.chips for p in game._players}
    payouts = compute_payouts(player_chips, game.buy_in, STARTING_CHIPS)

    for username, amount in payouts:
        if amount > 0:
            balance_store.credit(username, amount)

    game.offchain_settlement = payouts


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
                max_players=s.max_players,
                token=s.token,
                buy_in=s.buy_in,
                funded=s.funded,
                mode=s.mode or GameMode.OFFCHAIN,
            )
            for s in summaries
        ]
    )


@app.post("/api/games", response_model=CreateGameResponse)
def create_game(req: CreateGameRequest):
    # Infer mode: token present → onchain, else → offchain
    if req.mode is not None:
        mode = req.mode
        if mode == GameMode.ONCHAIN and not req.token:
            raise HTTPException(status_code=400, detail="On-chain mode requires a token address")
    else:
        mode = GameMode.ONCHAIN if req.token else GameMode.OFFCHAIN

    game_id, game = manager.create_game(
        max_players=req.max_players,
        token=req.token,
        buy_in=req.buy_in,
        mode=mode,
    )
    return CreateGameResponse(
        game_id=game_id,
        max_players=game.max_players,
        token=game.token,
        buy_in=game.buy_in,
        mode=game.mode or GameMode.OFFCHAIN,
    )


# ── Game-specific routes ─────────────────────────────────

@app.get("/game/{game_id}")
def game_page(game_id: int):
    _get_game_or_404(game_id)
    return FileResponse(STATIC_DIR / "spectator.html")


@app.post("/game/{game_id}/join", response_model=JoinGameResponse)
def join_game(game_id: int, req: JoinGameRequest, account: Account = Depends(require_auth)):
    game = _get_game_or_404(game_id)

    # Off-chain: debit buy-in from balance before registering
    if game.mode == GameMode.OFFCHAIN and game.buy_in > 0:
        try:
            balance_store.debit(account.username, game.buy_in)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance (need {game.buy_in})",
            )

    try:
        p = game.register(account.username, wallet_address=req.wallet_address)
    except ValueError as e:
        # Refund if registration failed (e.g. duplicate name)
        if game.mode == GameMode.OFFCHAIN and game.buy_in > 0:
            balance_store.credit(account.username, game.buy_in)
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

    # Off-chain games: balance was reserved at join time, mark funded
    if game.mode == GameMode.OFFCHAIN and game.buy_in > 0:
        game.funded = True

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


# ── Escrow routes ────────────────────────────────────────

@app.get("/game/{game_id}/escrow", response_model=EscrowInfoResponse)
def escrow_info(game_id: int):
    game = _get_game_or_404(game_id)
    if game.mode != GameMode.ONCHAIN:
        raise HTTPException(status_code=400, detail="Escrow only available for on-chain games")
    if game.buy_in <= 0:
        raise HTTPException(status_code=400, detail="Not a funded game")
    if not game.is_full:
        raise HTTPException(status_code=400, detail="Game is not full yet")

    from poker.escrow import (
        EscrowConfig,
        build_create_and_deposit_calldata,
        build_deposit_calldata,
        compute_escrow_address,
        generate_salt,
        get_env_config,
        get_server_address,
    )

    env = get_env_config()
    server_addr = get_server_address()
    if not server_addr:
        raise HTTPException(status_code=500, detail="Server private key not configured")
    if not env["factory_address"]:
        raise HTTPException(status_code=500, detail="Factory address not configured")

    # Generate escrow config on first call, cache on game for subsequent calls
    if game.escrow_config is None:
        import time as _time

        if game.escrow_salt is None:
            game.escrow_salt = generate_salt()

        wallets = tuple(
            p.wallet_address for p in game._players
            if p.wallet_address is not None
        )

        now = int(_time.time())
        cfg = EscrowConfig(
            token=game.token or "",
            admin=server_addr,
            rake_beneficiary=env["rake_beneficiary"] or server_addr,
            deposit_amount=game.buy_in,
            rake_bps=env["rake_bps"],
            funding_deadline=now + env["funding_timeout"],
            settlement_deadline=now + env["funding_timeout"] + env["settlement_timeout"],
            participants=wallets,
        )
        game.escrow_config = cfg
        game.escrow_address = compute_escrow_address(
            env["factory_address"], cfg, game.escrow_salt, rpc_url=env["base_rpc_url"],
        )

    cfg = game.escrow_config

    calldata_create = build_create_and_deposit_calldata(cfg, game.escrow_salt)
    calldata_deposits = {
        addr: build_deposit_calldata(addr)
        for addr in cfg.participants
    }

    return EscrowInfoResponse(
        escrow_address=game.escrow_address,
        factory_address=env["factory_address"],
        salt="0x" + game.escrow_salt.hex(),
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
        calldata_create_and_deposit=calldata_create,
        calldata_deposit=calldata_deposits,
        funding_deadline=cfg.funding_deadline,
        settlement_deadline=cfg.settlement_deadline,
    )


@app.get("/game/{game_id}/funding", response_model=FundingStatusResponse)
def funding_status(game_id: int):
    game = _get_game_or_404(game_id)
    if game.mode != GameMode.ONCHAIN:
        raise HTTPException(status_code=400, detail="Funding status only available for on-chain games")
    if game.buy_in <= 0:
        raise HTTPException(status_code=400, detail="Not a funded game")
    if game.escrow_address is None:
        raise HTTPException(status_code=400, detail="Escrow not yet configured (call /escrow first)")

    from poker.escrow import check_deposit_status, get_env_config

    env = get_env_config()
    wallets = tuple(
        p.wallet_address for p in game._players
        if p.wallet_address is not None
    )

    statuses = check_deposit_status(env["base_rpc_url"], game.escrow_address, wallets)
    all_deposited = all(deposited for _, deposited in statuses)

    if all_deposited:
        game.funded = True

    wallet_to_name: dict[str, str] = {}
    for p in game._players:
        if p.wallet_address:
            wallet_to_name[p.wallet_address.lower()] = p.name

    return FundingStatusResponse(
        all_deposited=all_deposited,
        deposits=[
            DepositStatus(
                address=addr,
                deposited=deposited,
                player_name=wallet_to_name.get(addr.lower()),
            )
            for addr, deposited in statuses
        ],
    )


@app.get("/game/{game_id}/settlement", response_model=SettlementResponse)
def settlement(game_id: int):
    game = _get_game_or_404(game_id)
    if game.mode != GameMode.ONCHAIN:
        raise HTTPException(status_code=400, detail="Settlement only available for on-chain games")
    if game.buy_in <= 0:
        raise HTTPException(status_code=400, detail="Not a funded game")
    if not game.game_over:
        raise HTTPException(status_code=400, detail="Game is not over yet")
    if game.escrow_address is None:
        raise HTTPException(status_code=400, detail="Escrow not configured")

    from poker.escrow import compute_payouts, get_env_config, sign_settlement

    env = get_env_config()
    if not env["server_private_key"]:
        raise HTTPException(status_code=500, detail="Server private key not configured")

    # Map player names → wallet addresses and chip counts
    player_chips: dict[str, int] = {}
    for p in game._players:
        if p.wallet_address:
            player_chips[p.wallet_address] = p.chips

    from poker.game import STARTING_CHIPS

    payouts = compute_payouts(player_chips, game.buy_in, STARTING_CHIPS)

    sig = sign_settlement(
        env["server_private_key"],
        env["chain_id"],
        game.escrow_address,
        payouts,
    )

    return SettlementResponse(
        payouts=[PayoutEntry(address=addr, amount=amt) for addr, amt in payouts],
        signature=sig,
        escrow_address=game.escrow_address,
    )


@app.get("/game/{game_id}/state/{player_id}", response_model=PlayerStateResponse)
def state(game_id: int, player_id: int):
    game = _get_game_or_404(game_id)
    rp = game.get_player(player_id)
    if rp is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    game._check_timeout()
    if game.game_over:
        _settle_offchain_game(game)

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
                is_resigned=getattr(game.get_player(p.id), 'resigned', False),
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
    game = _get_game_or_404(game_id)
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

    player = game.get_player_by_name(account.username)
    if player is None:
        raise HTTPException(status_code=404, detail="Not a player in this game")

    result = game.resign(player.id)
    if result == "ok":
        if game.game_over:
            _settle_offchain_game(game)
        return ActionResponse(success=True, message="Resigned from game")
    else:
        raise HTTPException(status_code=400, detail=result)


@app.post("/game/{game_id}/action", response_model=ActionResponse)
def action(game_id: int, req: ActionRequest, account: Account = Depends(require_auth)):
    game = _get_game_or_404(game_id)
    if not game.started:
        raise HTTPException(status_code=400, detail="Game not started")

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
        if game.game_over:
            _settle_offchain_game(game)
        return ActionResponse(success=True, message="Action accepted")
    else:
        raise HTTPException(status_code=400, detail=result)


def _build_spectator_response(game: Game, **overrides) -> SpectatorResponse:
    """Build a SpectatorResponse for a game, with optional field overrides."""
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
            buy_in=game.buy_in,
            escrow_address=game.escrow_address,
            mode=game.mode or GameMode.OFFCHAIN,
        )
        base.update(overrides)
        return SpectatorResponse(**base)

    side_pots = prev.get_side_pots_info()

    base = dict(
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
        buy_in=game.buy_in,
        escrow_address=game.escrow_address,
        mode=game.mode or GameMode.OFFCHAIN,
    )
    base.update(overrides)
    return SpectatorResponse(**base)


@app.get("/game/{game_id}/spectator", response_model=SpectatorResponse)
def spectator(game_id: int):
    game = _get_game_or_404(game_id)
    game._check_timeout()
    if game.game_over:
        _settle_offchain_game(game)
    return _build_spectator_response(game)


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
        stream = stream_manager.create_stream(game_id, account.username, title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CreateStreamResponse(stream_id=stream.id)


@app.get("/game/{game_id}/streams", response_model=StreamListResponse)
def list_streams_for_game(game_id: int):
    _get_game_or_404(game_id)
    summaries = stream_manager.list_streams_for_game(game_id)
    return StreamListResponse(
        streams=[
            StreamListItem(id=s.id, game_id=s.game_id, host=s.host_username, title=s.title)
            for s in summaries
        ]
    )


@app.get("/api/streams", response_model=StreamListResponse)
def list_all_streams():
    summaries = stream_manager.list_all_streams()
    return StreamListResponse(
        streams=[
            StreamListItem(id=s.id, game_id=s.game_id, host=s.host_username, title=s.title)
            for s in summaries
        ]
    )


@app.post("/stream/{stream_id}/commentate", response_model=CommentateResponse)
def stream_commentate(stream_id: int, req: CommentateRequest, account: Account = Depends(require_auth)):
    stream = stream_manager.get_stream(stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Stream not found")
    if stream.host_username != account.username:
        raise HTTPException(status_code=403, detail="Only the stream host can commentate")
    stream.commentary_text = req.text
    return CommentateResponse(success=True)


@app.get("/stream/{stream_id}")
def stream_page(stream_id: int):
    stream = stream_manager.get_stream(stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Stream not found")
    return FileResponse(STATIC_DIR / "spectator.html")


@app.get("/stream/{stream_id}/data", response_model=SpectatorResponse)
def stream_view(stream_id: int):
    stream = stream_manager.get_stream(stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Stream not found")
    game = manager.get_game(stream.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    game._check_timeout()
    if game.game_over:
        _settle_offchain_game(game)
    return _build_spectator_response(
        game,
        commentary_text=stream.commentary_text,
        stream_id=stream.id,
        stream_title=stream.title,
        stream_host=stream.host_username,
    )


# ── Bankroll routes ──────────────────────────────────

@app.post("/api/faucet", response_model=FaucetResponse)
def faucet(account: Account = Depends(require_auth)):
    try:
        bal = balance_store.try_claim_faucet(account.username, FAUCET_AMOUNT)
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

    from datetime import datetime, timedelta, timezone
    from poker.balance_store import FAUCET_COOLDOWN_SECONDS

    last = datetime.fromisoformat(bal.last_claim_at)
    next_claim = last + timedelta(seconds=FAUCET_COOLDOWN_SECONDS)

    return FaucetResponse(
        success=True,
        new_balance=bal.amount,
        next_claim_at=next_claim.isoformat(),
    )


@app.get("/api/balance", response_model=BalanceResponse)
def get_balance(account: Account = Depends(require_auth)):
    bal = balance_store.get(account.username)
    return BalanceResponse(username=account.username, balance=bal.amount)


@app.get("/game/{game_id}/offchain-settlement", response_model=OffchainSettlementResponse)
def offchain_settlement(game_id: int):
    game = _get_game_or_404(game_id)
    if game.mode != GameMode.OFFCHAIN:
        raise HTTPException(status_code=400, detail="Not an off-chain game")
    if not game.game_over:
        raise HTTPException(status_code=400, detail="Game is not over yet")
    if game.offchain_settlement is None:
        raise HTTPException(status_code=400, detail="Settlement not yet computed")

    return OffchainSettlementResponse(
        payouts=[
            OffchainPayout(username=name, amount=amt)
            for name, amt in game.offchain_settlement
        ]
    )
