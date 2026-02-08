from __future__ import annotations

import csv
import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path

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
    _CSV_HEADERS = ("username", "key_hash", "created_at")

    def __init__(self, csv_path: Path) -> None:
        self._csv_path = csv_path
        self._accounts: dict[str, Account] = {}
        self._load()

    def _load(self) -> None:
        if not self._csv_path.exists():
            self._csv_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_headers()
            return
        with open(self._csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                acct = Account(
                    username=row["username"],
                    key_hash=row["key_hash"],
                    created_at=row["created_at"],
                )
                self._accounts[acct.username] = acct

    def _write_headers(self) -> None:
        with open(self._csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self._CSV_HEADERS)

    def create_account(self, username: str) -> str:
        """Create an account and return the plaintext API key (shown once)."""
        if not username.strip():
            raise ValueError("Username cannot be empty")
        if username in self._accounts:
            raise ValueError(f"Username '{username}' already taken")

        api_key = generate_api_key()
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        acct = Account(username=username, key_hash=hash_key(api_key), created_at=now)

        self._accounts[username] = acct
        self._append_row(acct)
        return api_key

    def _append_row(self, acct: Account) -> None:
        with open(self._csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow((acct.username, acct.key_hash, acct.created_at))

    def verify_key(self, api_key: str) -> Account | None:
        """Return the Account if the key is valid, else None."""
        target_hash = hash_key(api_key)
        for acct in self._accounts.values():
            if acct.key_hash == target_hash:
                return acct
        return None

    def get_account(self, username: str) -> Account | None:
        return self._accounts.get(username)
