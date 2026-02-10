"""Admin router — runtime game type controls with API key auth."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException

from core.game_manager import GameManager

_log = logging.getLogger("poker.admin")

router = APIRouter(prefix="/admin", tags=["admin"])

_manager: GameManager | None = None
_admin_keys: frozenset[str] = frozenset()


def configure(*, mgr: GameManager, admin_keys: frozenset[str] | None = None) -> None:
    global _manager, _admin_keys
    _manager = mgr
    if admin_keys is not None:
        _admin_keys = admin_keys
    else:
        raw = os.environ.get("ADMIN_API_KEYS", "")
        _admin_keys = frozenset(k.strip() for k in raw.split(",") if k.strip())


def _require_admin(x_admin_key: str | None = Header(default=None)) -> str:
    if not _admin_keys:
        raise HTTPException(status_code=403, detail="Admin API keys not configured")
    if x_admin_key is None or x_admin_key not in _admin_keys:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return x_admin_key


def _get_manager() -> GameManager:
    if _manager is None:
        raise HTTPException(status_code=500, detail="Admin router not configured")
    return _manager


def _status_dict(mgr: GameManager) -> dict:
    return {
        "game_types": {
            gt: mgr.is_game_type_enabled(gt)
            for gt in sorted(mgr.registered_game_types)
        }
    }


@router.get("/status")
def admin_status(
    _key: str = Depends(_require_admin),
    mgr: GameManager = Depends(_get_manager),
):
    return _status_dict(mgr)


@router.post("/games/{game_type}/disable")
def disable_game_type(
    game_type: str,
    _key: str = Depends(_require_admin),
    mgr: GameManager = Depends(_get_manager),
):
    if game_type not in mgr.registered_game_types:
        raise HTTPException(status_code=404, detail=f"Unknown game type: {game_type!r}")
    mgr.disable_game_type(game_type)
    _log.info("admin_disable game_type=%s", game_type)
    return _status_dict(mgr)


@router.post("/games/{game_type}/enable")
def enable_game_type(
    game_type: str,
    _key: str = Depends(_require_admin),
    mgr: GameManager = Depends(_get_manager),
):
    try:
        mgr.enable_game_type(game_type)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown game type: {game_type!r}")
    _log.info("admin_enable game_type=%s", game_type)
    return _status_dict(mgr)
