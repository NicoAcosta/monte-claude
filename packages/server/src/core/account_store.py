from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass

from psycopg.errors import UniqueViolation
from psycopg_pool import ConnectionPool

_log = logging.getLogger("poker.account")

KEY_PREFIX = "pk_"


@dataclass(frozen=True)
class Account:
    username: str
    key_hash: str
    created_at: str


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


class AccountStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create_account(self, username: str) -> str:
        """Create an account and return the plaintext API key (shown once)."""
        if not username.strip():
            raise ValueError("Username cannot be empty")

        api_key = generate_api_key()
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        key_h = hash_key(api_key)

        with self._pool.connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO accounts (username, key_hash, created_at) VALUES (%s, %s, %s)",
                    (username, key_h, now),
                )
                conn.commit()
                _log.info("account_created user=%s", username)
            except UniqueViolation:
                conn.rollback()
                _log.warning("account_duplicate user=%s", username)
                raise ValueError(f"Username '{username}' already taken")

        return api_key

    def verify_key(self, api_key: str) -> Account | None:
        """Return the Account if the key is valid, else None."""
        target_hash = hash_key(api_key)
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT username, key_hash, created_at FROM accounts WHERE key_hash = %s",
                (target_hash,),
            ).fetchone()
        if row is None:
            return None
        return Account(username=row[0], key_hash=row[1], created_at=row[2])

    def get_account(self, username: str) -> Account | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT username, key_hash, created_at FROM accounts WHERE username = %s",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return Account(username=row[0], key_hash=row[1], created_at=row[2])
