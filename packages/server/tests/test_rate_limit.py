"""Unit tests for the sliding-window rate limiter."""

from unittest.mock import patch

from poker.rate_limit import RateLimitConfig, RateLimiter


def _make_limiter(max_requests: int = 3, window_seconds: int = 60) -> RateLimiter:
    return RateLimiter(RateLimitConfig(max_requests=max_requests, window_seconds=window_seconds))


class TestRateLimiter:
    def test_under_limit_allowed(self):
        limiter = _make_limiter(max_requests=3)
        assert limiter.check("ip1") is True
        assert limiter.check("ip1") is True
        assert limiter.check("ip1") is True

    def test_at_limit_blocks(self):
        limiter = _make_limiter(max_requests=2)
        assert limiter.check("ip1") is True
        assert limiter.check("ip1") is True
        assert limiter.check("ip1") is False

    def test_independent_keys(self):
        limiter = _make_limiter(max_requests=1)
        assert limiter.check("ip1") is True
        assert limiter.check("ip2") is True
        # ip1 is blocked, ip2 still has capacity exhausted too
        assert limiter.check("ip1") is False
        assert limiter.check("ip2") is False

    def test_window_expiry(self):
        limiter = _make_limiter(max_requests=1, window_seconds=10)
        # First request at t=100
        with patch("poker.rate_limit.time.monotonic", return_value=100.0):
            assert limiter.check("ip1") is True
        # Still blocked at t=105
        with patch("poker.rate_limit.time.monotonic", return_value=105.0):
            assert limiter.check("ip1") is False
        # Allowed again at t=111 (past the 10s window)
        with patch("poker.rate_limit.time.monotonic", return_value=111.0):
            assert limiter.check("ip1") is True

    def test_remaining_count(self):
        limiter = _make_limiter(max_requests=3)
        assert limiter.remaining("ip1") == 3
        limiter.check("ip1")
        assert limiter.remaining("ip1") == 2
        limiter.check("ip1")
        assert limiter.remaining("ip1") == 1
        limiter.check("ip1")
        assert limiter.remaining("ip1") == 0

    def test_clear(self):
        limiter = _make_limiter(max_requests=1)
        limiter.check("ip1")
        assert limiter.check("ip1") is False
        limiter.clear()
        assert limiter.check("ip1") is True
