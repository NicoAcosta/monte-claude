"""Thread-safe sliding-window rate limiter keyed by IP string."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitConfig:
    max_requests: int
    window_seconds: int


class RateLimiter:
    """Per-key sliding window rate limiter.

    Per-worker state only — no cross-worker coordination.
    """

    def __init__(self, config: RateLimitConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        now = time.monotonic()
        cutoff = now - self._config.window_seconds
        with self._lock:
            ts = self._timestamps[key]
            # Prune expired timestamps
            self._timestamps[key] = ts = [t for t in ts if t > cutoff]
            if len(ts) >= self._config.max_requests:
                return False
            ts.append(now)
            return True

    def remaining(self, key: str) -> int:
        """Return how many requests remain in the current window."""
        now = time.monotonic()
        cutoff = now - self._config.window_seconds
        with self._lock:
            ts = self._timestamps[key]
            active = [t for t in ts if t > cutoff]
            return max(0, self._config.max_requests - len(active))

    def clear(self) -> None:
        """Clear all tracked state. Used in tests."""
        with self._lock:
            self._timestamps.clear()
