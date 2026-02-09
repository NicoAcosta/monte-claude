from __future__ import annotations

import csv
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

FAUCET_COOLDOWN_SECONDS = 86400  # 24 hours


@dataclass(frozen=True)
class Balance:
    username: str
    amount: int
    last_claim_at: str  # ISO 8601 timestamp, or "" if never claimed


class BalanceStore:
    _CSV_HEADERS = ("username", "amount", "last_claim_at")

    def __init__(self, csv_path: Path) -> None:
        self._csv_path = csv_path
        self._balances: dict[str, Balance] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._lock_guard = threading.Lock()  # guards lock creation only
        self._load()

    def _user_lock(self, username: str) -> threading.Lock:
        with self._lock_guard:
            if username not in self._locks:
                self._locks[username] = threading.Lock()
            return self._locks[username]

    def _load(self) -> None:
        if not self._csv_path.exists():
            self._csv_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_headers()
            return
        with open(self._csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bal = Balance(
                    username=row["username"],
                    amount=int(row["amount"]),
                    last_claim_at=row["last_claim_at"],
                )
                self._balances[bal.username] = bal

    def _write_headers(self) -> None:
        with open(self._csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self._CSV_HEADERS)

    def _rewrite(self) -> None:
        fd, tmp = tempfile.mkstemp(dir=self._csv_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self._CSV_HEADERS)
                for bal in self._balances.values():
                    writer.writerow((bal.username, bal.amount, bal.last_claim_at))
            os.replace(tmp, self._csv_path)
        except BaseException:
            os.unlink(tmp)
            raise

    def get(self, username: str) -> Balance:
        """Return balance for username, defaulting to zero if unknown."""
        return self._balances.get(
            username, Balance(username=username, amount=0, last_claim_at="")
        )

    def credit(self, username: str, amount: int) -> Balance:
        """Add amount to user's balance. Returns updated Balance."""
        if amount < 0:
            raise ValueError("Credit amount must be non-negative")
        with self._user_lock(username):
            current = self.get(username)
            updated = Balance(
                username=username,
                amount=current.amount + amount,
                last_claim_at=current.last_claim_at,
            )
            self._balances[username] = updated
            self._rewrite()
            return updated

    def debit(self, username: str, amount: int) -> Balance:
        """Subtract amount from user's balance. Raises ValueError if insufficient."""
        if amount < 0:
            raise ValueError("Debit amount must be non-negative")
        with self._user_lock(username):
            current = self.get(username)
            if current.amount < amount:
                raise ValueError(
                    f"Insufficient balance: have {current.amount}, need {amount}"
                )
            updated = Balance(
                username=username,
                amount=current.amount - amount,
                last_claim_at=current.last_claim_at,
            )
            self._balances[username] = updated
            self._rewrite()
            return updated

    def try_claim_faucet(
        self,
        username: str,
        faucet_amount: int,
        *,
        now: datetime | None = None,
    ) -> Balance:
        """Claim daily faucet. Raises ValueError if cooldown not elapsed."""
        if now is None:
            now = datetime.now(timezone.utc)

        with self._user_lock(username):
            current = self.get(username)
            if current.last_claim_at:
                last = datetime.fromisoformat(current.last_claim_at)
                elapsed = (now - last).total_seconds()
                if elapsed < FAUCET_COOLDOWN_SECONDS:
                    remaining = int(FAUCET_COOLDOWN_SECONDS - elapsed)
                    raise ValueError(
                        f"Faucet cooldown: {remaining}s remaining"
                    )

            updated = Balance(
                username=username,
                amount=current.amount + faucet_amount,
                last_claim_at=now.isoformat(),
            )
            self._balances[username] = updated
            self._rewrite()
            return updated
