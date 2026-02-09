from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from psycopg_pool import ConnectionPool

from poker.db import timed_query

_log = logging.getLogger("poker.balance")

FAUCET_COOLDOWN_SECONDS = 86400  # 24 hours


@dataclass(frozen=True)
class Balance:
    username: str
    amount: int
    last_claim_at: str  # ISO 8601 timestamp, or "" if never claimed


class BalanceStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get(self, username: str) -> Balance:
        """Return balance for username, defaulting to zero if unknown."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT username, amount, last_claim_at FROM balances WHERE username = %s",
                (username,),
            ).fetchone()
        if row is None:
            return Balance(username=username, amount=0, last_claim_at="")
        return Balance(username=row[0], amount=row[1], last_claim_at=row[2])

    def credit(self, username: str, amount: int, *, reason: str = "") -> Balance:
        """Add amount to user's balance. Returns updated Balance."""
        if amount < 0:
            raise ValueError("Credit amount must be non-negative")
        now = datetime.now(timezone.utc)
        with timed_query("balance_credit"):
            with self._pool.connection() as conn:
                row = conn.execute(
                    """INSERT INTO balances (username, amount, last_claim_at)
                       VALUES (%s, %s, '')
                       ON CONFLICT (username) DO UPDATE
                       SET amount = balances.amount + EXCLUDED.amount
                       RETURNING username, amount, last_claim_at""",
                    (username, amount),
                ).fetchone()
                conn.execute(
                    """INSERT INTO balance_history (username, amount, balance_after, reason, created_at)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (username, amount, row[1], reason or "credit", now),
                )
                conn.commit()
        _log.info("credit user=%s amount=%d balance_after=%d reason=%s", username, amount, row[1], reason or "credit")
        return Balance(username=row[0], amount=row[1], last_claim_at=row[2])

    def debit(self, username: str, amount: int, *, reason: str = "") -> Balance:
        """Subtract amount from user's balance. Raises ValueError if insufficient."""
        if amount < 0:
            raise ValueError("Debit amount must be non-negative")
        now = datetime.now(timezone.utc)
        with timed_query("balance_debit"):
            with self._pool.connection() as conn:
                row = conn.execute(
                    "SELECT amount, last_claim_at FROM balances WHERE username = %s FOR UPDATE",
                    (username,),
                ).fetchone()
                if row is None:
                    _log.warning("debit_insufficient user=%s have=0 need=%d", username, amount)
                    raise ValueError(
                        f"Insufficient balance: have 0, need {amount}"
                    )
                current_amount = row[0]
                if current_amount < amount:
                    _log.warning("debit_insufficient user=%s have=%d need=%d", username, current_amount, amount)
                    raise ValueError(
                        f"Insufficient balance: have {current_amount}, need {amount}"
                    )
                new_amount = current_amount - amount
                conn.execute(
                    "UPDATE balances SET amount = %s WHERE username = %s",
                    (new_amount, username),
                )
                conn.execute(
                    """INSERT INTO balance_history (username, amount, balance_after, reason, created_at)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (username, -amount, new_amount, reason or "debit", now),
                )
                conn.commit()
                _log.info("debit user=%s amount=%d balance_after=%d reason=%s", username, amount, new_amount, reason or "debit")
                return Balance(username=username, amount=new_amount, last_claim_at=row[1])

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

        with timed_query("balance_faucet"):
            with self._pool.connection() as conn:
                row = conn.execute(
                    "SELECT amount, last_claim_at FROM balances WHERE username = %s FOR UPDATE",
                    (username,),
                ).fetchone()

                current_amount = row[0] if row else 0
                last_claim = row[1] if row else ""

                if last_claim:
                    last = datetime.fromisoformat(last_claim)
                    elapsed = (now - last).total_seconds()
                    if elapsed < FAUCET_COOLDOWN_SECONDS:
                        remaining = int(FAUCET_COOLDOWN_SECONDS - elapsed)
                        _log.warning("faucet_cooldown user=%s remaining=%ds", username, remaining)
                        raise ValueError(f"Faucet cooldown: {remaining}s remaining")

                new_amount = current_amount + faucet_amount
                now_iso = now.isoformat()

                conn.execute(
                    """INSERT INTO balances (username, amount, last_claim_at)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (username) DO UPDATE
                       SET amount = %s, last_claim_at = %s""",
                    (username, new_amount, now_iso, new_amount, now_iso),
                )
                conn.execute(
                    """INSERT INTO balance_history (username, amount, balance_after, reason, created_at)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (username, faucet_amount, new_amount, "faucet", now),
                )
                conn.commit()
                _log.info("faucet_claimed user=%s amount=%d balance_after=%d", username, faucet_amount, new_amount)
                return Balance(username=username, amount=new_amount, last_claim_at=now_iso)
