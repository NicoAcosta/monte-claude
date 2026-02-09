"""Single round of Over/Under dice — all logic, no side effects."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class RoundResult:
    dice: tuple[int, int]
    total: int
    category: str  # "low", "seven", "high"
    winner_ids: tuple[int, ...]
    pot: int
    payouts: dict[int, int]  # player_id → amount won (0 if lost)


def roll_dice() -> tuple[int, int]:
    return (random.randint(1, 6), random.randint(1, 6))


def categorize(total: int) -> str:
    if total <= 6:
        return "low"
    elif total == 7:
        return "seven"
    else:
        return "high"


def resolve_round(
    bets: dict[int, str],  # player_id → "high" | "low" | "seven"
    ante: int,
    dice: tuple[int, int] | None = None,
) -> RoundResult:
    """Resolve a round given player bets and ante.

    Args:
        bets: mapping of player_id to their chosen bet ("high", "low", "seven")
        ante: the ante amount each player paid
        dice: optional fixed dice for testing; if None, random roll

    Returns:
        RoundResult with dice, winners, and payout distribution.
    """
    if dice is None:
        dice = roll_dice()

    total = dice[0] + dice[1]
    category = categorize(total)
    pot = ante * len(bets)

    winner_ids = tuple(pid for pid, bet in bets.items() if bet == category)

    payouts: dict[int, int] = {}
    if winner_ids:
        share = pot // len(winner_ids)
        remainder = pot % len(winner_ids)
        for i, pid in enumerate(winner_ids):
            payouts[pid] = share + (1 if i < remainder else 0)

    for pid in bets:
        if pid not in payouts:
            payouts[pid] = 0

    return RoundResult(
        dice=dice,
        total=total,
        category=category,
        winner_ids=winner_ids,
        pot=pot,
        payouts=payouts,
    )
