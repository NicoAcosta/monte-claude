from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from poker.account_store import Account, AccountStore
from poker.audit import AuthAuditStore
from poker.logging_config import client_ip_var

_log = logging.getLogger("poker.auth")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def make_auth_dependency(
    get_store: Callable[[], AccountStore],
    get_audit: Callable[[], AuthAuditStore | None] | None = None,
):
    """Create an auth dependency that resolves the AccountStore at call time.

    Uses a callable (thunk) so the store can be swapped in tests.
    """

    def _record(event_type: str, username: str | None = None) -> None:
        if get_audit is None:
            return
        audit = get_audit()
        if audit is None:
            return
        try:
            audit.record(event_type, username=username, ip=client_ip_var.get(""))
        except Exception:
            _log.debug("auth_audit_write_failed event=%s", event_type, exc_info=True)

    def require_auth(api_key: str | None = Security(api_key_header)) -> Account:
        if api_key is None:
            _log.warning("auth_failure reason=missing_key")
            _record("login_failure_missing_key")
            raise HTTPException(status_code=401, detail="Missing API key")
        account = get_store().verify_key(api_key)
        if account is None:
            _log.warning("auth_failure reason=invalid_key")
            _record("login_failure_invalid_key")
            raise HTTPException(status_code=401, detail="Invalid API key")
        _record("login_success", username=account.username)
        return account

    return require_auth
