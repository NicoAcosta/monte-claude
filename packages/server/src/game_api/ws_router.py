"""WebSocket router — real-time game state push for players and spectators."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.account_store import AccountStore
from core.event_bus import GameEventBus, Subscriber
from core.game_manager import GameManager
from core.state_builders import (
    build_dice_player_state,
    build_dice_spectator_state,
    build_poker_player_state,
    build_poker_spectator_state,
)

_log = logging.getLogger("game_api.ws")

router = APIRouter()

# ── Dependency injection (set by game_api.app during startup) ─────

_manager: GameManager | None = None
_account_store: AccountStore | None = None
_event_bus: GameEventBus | None = None

_PING_INTERVAL = 30.0  # seconds between heartbeat pings


def configure(
    *,
    mgr: GameManager,
    acc: AccountStore,
    bus: GameEventBus,
) -> None:
    """Inject shared stores from the application layer."""
    global _manager, _account_store, _event_bus
    _manager = mgr
    _account_store = acc
    _event_bus = bus


# ── Helpers ───────────────────────────────────────────────────────


def _build_player_state_dict(game, config, player_id: int, game_type: str) -> dict:
    """Build player state as a serialisable dict, dispatching by game type."""
    if game_type == "dice":
        return build_dice_player_state(game, config, player_id).model_dump()
    return build_poker_player_state(game, config, player_id).model_dump()


def _build_spectator_state_dict(game, config, game_type: str) -> dict:
    """Build spectator state as a serialisable dict, dispatching by game type."""
    if game_type == "dice":
        return build_dice_spectator_state(game, config).model_dump()
    return build_poker_spectator_state(game, config).model_dump()


async def _send_error(ws: WebSocket, detail: str) -> None:
    """Send an error message over the WebSocket."""
    try:
        await ws.send_json({"type": "error", "detail": detail})
    except Exception:
        pass


async def _event_listener(
    ws: WebSocket,
    sub: Subscriber,
    state_builder,
) -> None:
    """Read events from the subscriber queue, build fresh state, send to client.

    Sends a ping if no events arrive within PING_INTERVAL seconds.
    Exits on WebSocketDisconnect or send failure.
    """
    while True:
        try:
            event_type, data = await asyncio.wait_for(sub.get(), timeout=_PING_INTERVAL)
        except asyncio.TimeoutError:
            # Heartbeat ping
            try:
                await ws.send_json({"type": "ping", "ts": time.time()})
            except Exception:
                return
            continue

        # Build and send fresh state
        try:
            state_data, state_version = state_builder()
            await ws.send_json({
                "type": "state",
                "state_version": state_version,
                "data": state_data,
            })
        except WebSocketDisconnect:
            return
        except Exception:
            _log.exception("ws_send_state_failed")
            return


async def _client_reader(ws: WebSocket) -> None:
    """Read from client until disconnect (detects closure)."""
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        return
    except Exception:
        return


# ── Endpoints ─────────────────────────────────────────────────────


@router.websocket("/ws/game/{game_id}/player")
async def player_ws(websocket: WebSocket, game_id: str, api_key: str | None = None):
    """Authenticated player WebSocket — receives personalised game state on every event."""
    assert _manager is not None and _account_store is not None and _event_bus is not None

    # 1. Validate api_key
    if not api_key:
        await websocket.accept()
        await _send_error(websocket, "Missing api_key query parameter")
        await websocket.close(code=4001)
        return

    account = _account_store.verify_key(api_key)
    if account is None:
        await websocket.accept()
        await _send_error(websocket, "Invalid API key")
        await websocket.close(code=4001)
        return

    # 2. Look up game
    game = _manager.get_game(game_id)
    config = _manager.get_config(game_id)
    game_type = _manager.get_game_type(game_id)
    if game is None or config is None or game_type is None:
        await websocket.accept()
        await _send_error(websocket, "Game not found")
        await websocket.close(code=4004)
        return

    # 3. Find player in game by username
    player = game.get_player_by_name(account.username)
    if player is None:
        await websocket.accept()
        await _send_error(websocket, "You are not a player in this game")
        await websocket.close(code=4003)
        return

    # 4. Accept
    await websocket.accept()

    # 5. Subscribe to event bus
    sub = _event_bus.subscribe(game_id)

    try:
        # 6. Send initial state
        game._check_timeout()
        state_data = _build_player_state_dict(game, config, player.id, game_type)
        await websocket.send_json({
            "type": "state",
            "state_version": game.state_version,
            "data": state_data,
        })

        # 7. Run event listener + client reader concurrently
        def _build():
            game._check_timeout()
            return _build_player_state_dict(game, config, player.id, game_type), game.state_version

        listener = asyncio.create_task(_event_listener(websocket, sub, _build))
        reader = asyncio.create_task(_client_reader(websocket))

        done, pending = await asyncio.wait(
            {listener, reader},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        pass
    except Exception:
        _log.exception("player_ws_error game_id=%s user=%s", game_id, account.username)
    finally:
        # 8. Cleanup
        _event_bus.unsubscribe(sub)


@router.websocket("/ws/game/{game_id}/spectator")
async def spectator_ws(websocket: WebSocket, game_id: str):
    """Unauthenticated spectator WebSocket — receives public game state on every event."""
    assert _manager is not None and _event_bus is not None

    # 1. Look up game
    game = _manager.get_game(game_id)
    config = _manager.get_config(game_id)
    game_type = _manager.get_game_type(game_id)
    if game is None or config is None or game_type is None:
        await websocket.accept()
        await _send_error(websocket, "Game not found")
        await websocket.close(code=4004)
        return

    # 2. Accept
    await websocket.accept()

    # 3. Subscribe to event bus
    sub = _event_bus.subscribe(game_id)

    try:
        # 4. Send initial state
        game._check_timeout()
        state_data = _build_spectator_state_dict(game, config, game_type)
        await websocket.send_json({
            "type": "state",
            "state_version": game.state_version,
            "data": state_data,
        })

        # 5. Run event listener + client reader concurrently
        def _build():
            game._check_timeout()
            return _build_spectator_state_dict(game, config, game_type), game.state_version

        listener = asyncio.create_task(_event_listener(websocket, sub, _build))
        reader = asyncio.create_task(_client_reader(websocket))

        done, pending = await asyncio.wait(
            {listener, reader},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        pass
    except Exception:
        _log.exception("spectator_ws_error game_id=%s", game_id)
    finally:
        # 6. Cleanup
        _event_bus.unsubscribe(sub)
