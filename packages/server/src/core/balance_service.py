"""Faucet and balance operations — pure service functions."""

from __future__ import annotations

from datetime import datetime, timedelta

from core.balance_store import FAUCET_COOLDOWN_SECONDS, Balance, BalanceStore


def claim_faucet(
    store: BalanceStore,
    username: str,
    amount: int,
) -> tuple[Balance, str]:
    """Claim faucet tokens. Returns (updated_balance, next_claim_iso).

    Raises ValueError if cooldown not elapsed.
    """
    bal = store.try_claim_faucet(username, amount)
    last = datetime.fromisoformat(bal.last_claim_at)
    next_claim = last + timedelta(seconds=FAUCET_COOLDOWN_SECONDS)
    return bal, next_claim.isoformat()
