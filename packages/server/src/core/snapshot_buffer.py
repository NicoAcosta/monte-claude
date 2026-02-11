"""Per-game ring buffer for spectator state snapshots.

Each game accumulates snapshots (one per game event) so that spectator
clients can poll for incremental updates and replay them with delays.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field


SPECTATOR_DELAY = 30.0  # seconds before spectators see a snapshot

@dataclass
class Snapshot:
    sequence: int
    state: dict
    timestamp: float = field(default_factory=time.time)


class SnapshotBuffer:
    """Thread-safe per-game ring buffer of spectator state snapshots."""

    def __init__(self, max_per_game: int = 200) -> None:
        self._max = max_per_game
        self._delay = SPECTATOR_DELAY
        self._buffers: dict[str, deque[Snapshot]] = {}
        self._lock = threading.Lock()

    def append(self, game_id: str, sequence: int, state: dict) -> None:
        with self._lock:
            buf = self._buffers.get(game_id)
            if buf is None:
                buf = deque(maxlen=self._max)
                self._buffers[game_id] = buf
            # Skip if the sequence hasn't advanced (e.g. events during Hand.__init__)
            if buf and buf[-1].sequence == sequence:
                return
            buf.append(Snapshot(sequence=sequence, state=state))

    def get_since(self, game_id: str, after_sequence: int) -> list[dict]:
        """Return snapshot state dicts with sequence > after_sequence, respecting delay."""
        with self._lock:
            buf = self._buffers.get(game_id)
            if buf is None:
                return []
            cutoff = time.time() - self._delay
            return [
                s.state for s in buf
                if s.sequence > after_sequence and s.timestamp <= cutoff
            ]

    def get_delayed_latest(self, game_id: str) -> dict | None:
        """Return the most recent snapshot old enough per the delay, or None."""
        if self._delay <= 0:
            return None
        with self._lock:
            buf = self._buffers.get(game_id)
            if buf is None:
                return None
            cutoff = time.time() - self._delay
            for s in reversed(buf):
                if s.timestamp <= cutoff:
                    return s.state
            return None

    def cleanup(self, game_id: str) -> None:
        with self._lock:
            self._buffers.pop(game_id, None)
