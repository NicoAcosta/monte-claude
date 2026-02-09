"""Account API — registration, faucet, balance (port 8002)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from prometheus_fastapi_instrumentator import Instrumentator

from core.logging_config import configure_logging, RequestContextMiddleware, client_ip_var

configure_logging()

_log = logging.getLogger("poker.account_api")

from core.account_store import Account, AccountStore
from core.audit import AuthAuditStore
from core.auth import make_auth_dependency
from core.balance_store import BalanceStore
from core.db import get_pool
from poker.models import (
    AccountRegisterRequest,
    AccountRegisterResponse,
    BalanceResponse,
    FaucetResponse,
)
from core.rate_limit import RateLimitConfig, RateLimiter
from core import balance_service

# ── Rate limiters ────────────────────────────────────────
# Limits are intentionally high (effectively infinite) for now.
# Tighten when spam becomes a concern (e.g. max_requests=5 for register).
_register_limiter = RateLimiter(RateLimitConfig(max_requests=1_000_000, window_seconds=3600))
_faucet_limiter = RateLimiter(RateLimitConfig(max_requests=1_000_000, window_seconds=3600))

# ── Lazy-init stores (same pattern as Data API) ─────────
account_store: AccountStore | None = None
balance_store: BalanceStore | None = None
auth_audit: AuthAuditStore | None = None

require_auth = make_auth_dependency(lambda: account_store, get_audit=lambda: auth_audit)

FAUCET_AMOUNT = 10_000


def _ensure_stores() -> None:
    """Create stores on first call — safe to call after fork."""
    global account_store, balance_store, auth_audit
    if account_store is not None:
        return
    pool = get_pool()
    account_store = AccountStore(pool)
    balance_store = BalanceStore(pool)
    auth_audit = AuthAuditStore(pool)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    _ensure_stores()
    yield


app = FastAPI(title="Monteclaude — Account API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception):
    _log.exception("unhandled_exception path=%s", request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.get("/health")
def health():
    pool = get_pool()
    stats = pool.get_stats()
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "healthy" if db_ok else "degraded",
        "db": db_ok,
        "pool": {
            "size": stats["pool_size"],
            "available": stats["pool_available"],
            "waiting": stats["requests_waiting"],
        },
    }


# ── Account routes ───────────────────────────────────────

@app.post("/api/register", response_model=AccountRegisterResponse)
def register_account(req: AccountRegisterRequest, request: Request):
    ip = client_ip_var.get("")
    if not _register_limiter.check(ip):
        raise HTTPException(
            status_code=429,
            detail="Registration rate limit exceeded. Try again later.",
        )
    try:
        api_key = account_store.create_account(req.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AccountRegisterResponse(api_key=api_key, username=req.username)


@app.post("/api/faucet", response_model=FaucetResponse)
def faucet(request: Request, account: Account = Depends(require_auth)):
    ip = client_ip_var.get("")
    if not _faucet_limiter.check(ip):
        raise HTTPException(
            status_code=429,
            detail="Faucet rate limit exceeded. Try again later.",
        )
    try:
        bal, next_claim_at = balance_service.claim_faucet(
            balance_store, account.username, FAUCET_AMOUNT,
        )
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

    return FaucetResponse(
        success=True,
        new_balance=bal.amount,
        next_claim_at=next_claim_at,
    )


@app.get("/api/balance", response_model=BalanceResponse)
def get_balance(account: Account = Depends(require_auth)):
    bal = balance_store.get(account.username)
    return BalanceResponse(username=account.username, balance=bal.amount)
