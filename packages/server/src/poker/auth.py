from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from poker.account_store import Account, AccountStore

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def make_auth_dependency(get_store: Callable[[], AccountStore]):
    """Create an auth dependency that resolves the AccountStore at call time.

    Uses a callable (thunk) so the store can be swapped in tests.
    """

    def require_auth(api_key: str | None = Security(api_key_header)) -> Account:
        if api_key is None:
            raise HTTPException(status_code=401, detail="Missing API key")
        account = get_store().verify_key(api_key)
        if account is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return account

    return require_auth
