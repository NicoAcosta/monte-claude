"""Async HTTP client for the Monteclaude poker API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

_RETRY_STATUSES = frozenset({409, 429, 502, 503, 504})
_MAX_RETRIES = 3
_RETRY_DELAY = 1.0


@dataclass(frozen=True)
class GameConfig:
    game_id: int
    api_key: str
    player_id: int
    username: str


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


class Client:
    """Thin wrapper around the Monteclaude HTTP API."""

    def __init__(self, server: str, *, game_server: str | None = None, account_server: str | None = None) -> None:
        self._game = httpx.AsyncClient(base_url=game_server or server, timeout=30.0)
        self._account = httpx.AsyncClient(base_url=account_server or server, timeout=30.0)

    async def close(self) -> None:
        await self._game.aclose()
        await self._account.aclose()

    # ── Account API ──────────────────────────────────

    async def register(self, username: str) -> str:
        """Register and return the API key."""
        resp = await self._account.post(
            "/api/accounts/register", json={"username": username},
        )
        _check(resp)
        return resp.json()["api_key"]

    async def get_balance(self, api_key: str) -> int:
        """Get current token balance."""
        resp = await self._account.get("/api/accounts/balance", headers=_auth(api_key))
        _check(resp)
        return resp.json()["balance"]

    async def claim_faucet(self, api_key: str) -> dict[str, Any]:
        """Claim faucet tokens. Returns {success, new_balance, next_claim_at}.

        Raises ApiError(429) if faucet is on cooldown.
        """
        resp = await self._account.post("/api/accounts/faucet", headers=_auth(api_key))
        _check(resp)
        return resp.json()

    # ── Game API ─────────────────────────────────────

    async def create_game(self, api_key: str, max_players: int = 2, game_type: str = "poker") -> int:
        """Create a new free game and return game_id."""
        resp = await self._game.post(
            "/api/games",
            json={"game_type": game_type, "max_players": max_players},
            headers=_auth(api_key),
        )
        _check(resp)
        return resp.json()["game_id"]

    async def join_game(self, game_id: int, api_key: str) -> dict[str, Any]:
        """Join a game. Returns {player_id, name}."""
        resp = await self._game.post(
            f"/api/games/{game_id}/join",
            json={},
            headers=_auth(api_key),
        )
        _check(resp)
        return resp.json()

    async def start_game(self, game_id: int, api_key: str) -> None:
        """Start a game."""
        resp = await self._game.post(
            f"/api/games/{game_id}/start",
            json={},
            headers=_auth(api_key),
        )
        _check(resp)

    async def get_waiting(self, game_id: int) -> dict[str, Any]:
        """Get waiting room status."""
        resp = await self._game.get(f"/api/games/{game_id}/waiting")
        _check(resp)
        return resp.json()

    async def wait_for_start(self, game_id: int, poll_interval: float = 1.0) -> None:
        """Poll /waiting until game starts."""
        while True:
            data = await self.get_waiting(game_id)
            if data["started"]:
                return
            log.info("Waiting for game to start... (%d players)", data["player_count"])
            await asyncio.sleep(poll_interval)

    async def get_state(self, game_id: int, api_key: str) -> dict[str, Any]:
        """Get player state."""
        resp = await self._game.get(
            f"/api/games/{game_id}/state", headers=_auth(api_key),
        )
        _check(resp)
        return resp.json()

    async def do_action(
        self,
        game_id: int,
        api_key: str,
        action: str,
        amount: int | None = None,
        comment: str | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        """Submit an action with retry on 409/transient errors."""
        body: dict[str, Any] = {"action": action}
        if amount is not None:
            body["amount"] = amount
        if comment is not None:
            body["comment"] = comment
        if expected_version is not None:
            body["expected_version"] = expected_version

        for attempt in range(_MAX_RETRIES):
            resp = await self._game.post(
                f"/api/games/{game_id}/action",
                json=body,
                headers=_auth(api_key),
            )
            if resp.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAY * (attempt + 1)
                log.warning(
                    "Action got %d, retrying in %.1fs (attempt %d/%d)",
                    resp.status_code, delay, attempt + 1, _MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                continue
            _check(resp)
            return resp.json()

        # Should not reach here, but satisfy type checker
        _check(resp)  # type: ignore[possibly-undefined]
        return resp.json()  # type: ignore[possibly-undefined]


def _auth(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def _check(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise ApiError(resp.status_code, detail)
