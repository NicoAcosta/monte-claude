"""Pure payout math — maps final chip counts to token payout amounts."""

from __future__ import annotations


def compute_payouts(
    player_chips: dict[str, int],
    buy_in: int,
    starting_chips: int,
) -> list[tuple[str, int]]:
    """Map final chip counts to token payout amounts.

    payout_i = chips_i * buy_in / starting_chips

    The sum of all payouts equals total deposits (num_players * buy_in).
    Rounding dust is given to the largest winner.
    """
    if starting_chips <= 0:
        raise ValueError("starting_chips must be positive")
    if buy_in < 0:
        raise ValueError("buy_in must be non-negative")
    if not player_chips:
        raise ValueError("player_chips cannot be empty")

    total_deposits = len(player_chips) * buy_in

    # Compute raw payouts
    raw: list[tuple[str, int]] = []
    for addr, chips in player_chips.items():
        raw.append((addr, (chips * buy_in) // starting_chips))

    # Fix rounding dust: assign remainder to the player with most chips
    payout_sum = sum(amount for _, amount in raw)
    dust = total_deposits - payout_sum

    if dust > 0:
        max_idx = max(range(len(raw)), key=lambda i: raw[i][1])
        addr, amount = raw[max_idx]
        raw[max_idx] = (addr, amount + dust)

    return raw
