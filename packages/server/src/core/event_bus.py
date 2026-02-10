"""In-process event bus for pushing game state over WebSocket.

Single-worker architecture: no external pub/sub needed.
Each subscriber gets an asyncio.Queue for backpressure control.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger(__name__)

# Type alias for events: (event_type, data)
Event = tuple[str, dict[str, Any]]


@dataclass
class Subscriber:
    """A single WebSocket connection's subscription to game events."""

    game_id: str
    _queue: asyncio.Queue[Event] = field(repr=False)

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: object) -> bool:
        return self is other

    async def get(self) -> Event:
        """Wait for and return the next event."""
        return await self._queue.get()

    def get_nowait(self) -> Event | None:
        """Return next event if available, else None."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


class GameEventBus:
    """In-process pub/sub keyed by game_id.

    Thread-safe for single-threaded asyncio use (no locking needed).
    """

    def __init__(self, max_queue_size: int = 64) -> None:
        self._subscribers: dict[str, set[Subscriber]] = {}
        self._max_queue_size = max_queue_size

    def subscribe(self, game_id: str) -> Subscriber:
        """Create a new subscriber for the given game."""
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._max_queue_size)
        sub = Subscriber(game_id=game_id, _queue=queue)
        if game_id not in self._subscribers:
            self._subscribers[game_id] = set()
        self._subscribers[game_id].add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        """Remove a subscriber. Idempotent."""
        subs = self._subscribers.get(sub.game_id)
        if subs:
            subs.discard(sub)
            if not subs:
                del self._subscribers[sub.game_id]

    def publish(self, game_id: str, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers of a game.

        Non-blocking: if a subscriber's queue is full (slow consumer),
        the event is dropped for that subscriber and a warning is logged.
        """
        subs = self._subscribers.get(game_id)
        if not subs:
            return
        event: Event = (event_type, data)
        for sub in subs:
            try:
                sub._queue.put_nowait(event)
            except asyncio.QueueFull:
                _log.warning(
                    "event_bus_queue_full game_id=%s event=%s — dropping for slow consumer",
                    game_id,
                    event_type,
                )

    def cleanup_game(self, game_id: str) -> None:
        """Remove all subscribers for a game (e.g., on game_over)."""
        self._subscribers.pop(game_id, None)

    def subscriber_count(self, game_id: str) -> int:
        """Return the number of subscribers for a game."""
        return len(self._subscribers.get(game_id, set()))

    @property
    def total_subscribers(self) -> int:
        """Return the total number of subscribers across all games."""
        return sum(len(s) for s in self._subscribers.values())
