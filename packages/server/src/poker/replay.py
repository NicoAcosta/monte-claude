from __future__ import annotations

import json
from dataclasses import dataclass, replace

from poker.history_models import GameEvent


@dataclass(frozen=True)
class PlayerSnapshot:
    id: int
    name: str
    chips: int
    hole_cards: tuple[str, ...] = ()
    current_bet: int = 0
    is_folded: bool = False
    is_all_in: bool = False


@dataclass(frozen=True)
class GameSnapshot:
    hand_number: int
    phase: str
    community_cards: tuple[str, ...] = ()
    pot: int = 0
    players: tuple[PlayerSnapshot, ...] = ()
    current_turn: int | None = None
    dealer_id: int = 0


def _initial_snapshot() -> GameSnapshot:
    return GameSnapshot(hand_number=0, phase="waiting")


def apply_event(state: GameSnapshot, event: GameEvent) -> GameSnapshot:
    """Pure function: state + event -> new state."""
    data = json.loads(event.data)

    if event.event_type == "hand_started":
        players = tuple(
            PlayerSnapshot(id=p["id"], name=p["name"], chips=p["chips"])
            for p in data.get("players", [])
        )
        return GameSnapshot(
            hand_number=data.get("hand_number", state.hand_number),
            phase="preflop",
            community_cards=(),
            pot=0,
            players=players,
            dealer_id=data.get("dealer_id", 0),
        )

    if event.event_type == "cards_dealt":
        player_id = data.get("player_id")
        cards = tuple(data.get("cards", []))
        new_players = tuple(
            replace(p, hole_cards=cards) if p.id == player_id else p
            for p in state.players
        )
        return replace(state, players=new_players)

    if event.event_type == "action":
        return _apply_action(state, data)

    if event.event_type == "community_dealt":
        new_cards = state.community_cards + tuple(data.get("cards", []))
        new_phase = data.get("phase", state.phase)
        # Reset current bets on new street
        new_players = tuple(
            replace(p, current_bet=0) for p in state.players
        )
        return replace(
            state,
            community_cards=new_cards,
            phase=new_phase,
            players=new_players,
        )

    if event.event_type == "hand_completed":
        return replace(state, phase="complete")

    if event.event_type == "game_over":
        return replace(state, phase="game_over")

    # player_joined, game_started, player_eliminated — no state change needed
    return state


def _apply_action(state: GameSnapshot, data: dict) -> GameSnapshot:
    action = data.get("action", "")
    player_name = data.get("player_name", "")
    amount = data.get("amount")

    new_players = list(state.players)
    new_pot = state.pot

    for i, p in enumerate(new_players):
        if p.name != player_name:
            continue

        if action == "fold":
            new_players[i] = replace(p, is_folded=True)
        elif action in ("small_blind", "big_blind", "bet", "raise", "call"):
            bet_amount = amount if amount is not None else 0
            chip_cost = bet_amount - p.current_bet
            new_chips = p.chips - chip_cost
            is_all_in = new_chips == 0
            new_pot += chip_cost
            new_players[i] = replace(
                p, chips=new_chips, current_bet=bet_amount, is_all_in=is_all_in,
            )
        elif action == "all_in":
            bet_amount = amount if amount is not None else p.chips + p.current_bet
            chip_cost = bet_amount - p.current_bet
            new_pot += chip_cost
            new_players[i] = replace(
                p, chips=0, current_bet=bet_amount, is_all_in=True,
            )
        # "check" — no state change
        break

    return replace(state, players=tuple(new_players), pot=new_pot)


def replay_game(events: list[GameEvent]) -> list[GameSnapshot]:
    """Replay all events, return snapshot at each step.

    Returns a list of (len(events) + 1) snapshots:
    [initial_state, state_after_event_0, state_after_event_1, ...]
    """
    state = _initial_snapshot()
    snapshots = [state]
    for event in events:
        state = apply_event(state, event)
        snapshots.append(state)
    return snapshots


def replay_to(events: list[GameEvent], step: int) -> GameSnapshot:
    """Replay events up to a given step index (0-based event index)."""
    state = _initial_snapshot()
    for event in events[: step + 1]:
        state = apply_event(state, event)
    return state
