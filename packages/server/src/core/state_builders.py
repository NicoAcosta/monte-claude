"""Pure state builders — construct player/spectator responses from game state.

No HTTP concerns (no HTTPException). These are pure functions used by routers
and (soon) WebSocket handlers.
"""

from __future__ import annotations

from typing import Any

from core.game_config import GameConfig
from core.game_mode import GameMode
from core.models import ChatMessage, PlayerComment, RecentAction, TimerInfo
from dice.game import DiceGame
from dice.models import (
    DicePlayerState,
    DiceSpectatorPlayerState,
    DiceSpectatorResponse,
    DiceStateResponse,
)
from poker.game import BIG_BLIND, Game, SMALL_BLIND
from poker.models import (
    PlayerPublicState,
    PlayerStateResponse,
    SidePotInfo,
    SpectatorPlayerState,
    SpectatorResponse,
)


# ── Shared helpers ────────────────────────────────────────


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


def _recent_actions(game: Game, include_reason: bool = False) -> list[RecentAction]:
    actions = game.recent_actions
    if game.current_hand:
        actions = game.current_hand.actions
    return [_action_to_recent(a, include_reason) for a in actions[-20:]]


def _player_comments(game: Game) -> list[PlayerComment]:
    actions = game.current_hand.actions if game.current_hand else game.recent_actions
    latest: dict[str, str] = {}
    for a in actions:
        if a.comment:
            latest[a.player_name] = a.comment
    return [PlayerComment(player=name, comment=text) for name, text in latest.items()]


def _chat_log(game: Game | DiceGame) -> list[ChatMessage]:
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


# ── Poker builders ────────────────────────────────────────


def build_poker_spectator_state(
    game: Game, config: GameConfig, **overrides: Any,
) -> SpectatorResponse:
    """Build spectator response from game state. Pure function, no HTTP concerns."""
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


def build_poker_player_state(
    game: Game, config: GameConfig, player_id: int,
) -> PlayerStateResponse:
    """Build player state response. Caller must resolve name→id and verify game started."""
    rp = game.get_player(player_id)

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
            your_chips=rp.chips if rp else 0,
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
    your_chips = hand_player.chips if hand_player else (rp.chips if rp else 0)
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


# ── Dice builders ─────────────────────────────────────────


def _dice_chat_log(game: DiceGame) -> list[dict]:
    return [
        {"player": name, "message": msg, "timestamp": ts}
        for name, msg, ts in game.chat_log
    ]


def build_dice_spectator_state(
    game: DiceGame, config: GameConfig, **overrides: Any,
) -> DiceSpectatorResponse:
    """Build dice spectator response. Pure function, no HTTP concerns."""
    current = game.current_player
    bets = game.bets
    result = game.last_result

    base = dict(
        started=game.started,
        game_over=game.game_over,
        winner=game.winner,
        round_number=game.hand_number,
        phase=game.phase,
        ante=game.ante,
        players=[
            DiceSpectatorPlayerState(
                id=p.id,
                name=p.name,
                chips=p.chips,
                resigned=p.resigned,
                is_current=current is not None and current.id == p.id,
                bet=bets.get(p.id),
            )
            for p in game.players
        ],
        last_dice=list(result.dice) if result else None,
        last_total=result.total if result else None,
        last_category=result.category if result else None,
        last_winner_ids=list(result.winner_ids) if result else None,
        last_pot=result.pot if result else None,
        turn_deadline=game.turn_deadline,
        chat=_dice_chat_log(game),
        state_version=game.state_version,
        seed_commitment=game.seed_commitment,
    )
    base.update(overrides)
    return DiceSpectatorResponse(**base)


def build_dice_player_state(
    game: DiceGame, config: GameConfig, player_id: int,
) -> DiceStateResponse:
    """Build dice player state response. Caller must resolve name→id and verify game started."""
    rp = game.get_player(player_id)

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
        your_player_id=player_id,
        your_chips=rp.chips if rp else 0,
        your_bet=bets.get(player_id),
        is_your_turn=current is not None and current.id == player_id,
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
        extensions_remaining=game.get_extensions_remaining(player_id),
        chat=_dice_chat_log(game),
        state_version=game.state_version,
        seed_commitment=game.seed_commitment,
    )
