"""Minimal in-process TTL cache — no external dependencies."""

from __future__ import annotations

import threading
import time


class TTLCache:
    """Thread-safe dict with per-key expiration."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[object, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> object | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: object, ttl: float) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic() + ttl)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
