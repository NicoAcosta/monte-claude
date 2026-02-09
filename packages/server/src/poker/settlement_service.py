"""Off-chain settlement — compute payouts and credit balances."""

from __future__ import annotations

from poker.balance_store import BalanceStore
from poker.game import Game, STARTING_CHIPS
from poker.game_config import GameConfig
from poker.game_mode import GameMode
from poker.payout import compute_payouts


def settle_offchain_game(
    game: Game,
    config: GameConfig,
    balance_store: BalanceStore,
) -> None:
    """Compute and credit offchain payouts when a game ends.

    Idempotent — does nothing if already settled, wrong mode, or zero buy-in.
    """
    if config.mode != GameMode.OFFCHAIN or config.buy_in <= 0:
        return
    if config.offchain_settlement is not None:
        return

    player_chips: dict[str, int] = {p.name: p.chips for p in game._players}
    payouts = compute_payouts(player_chips, config.buy_in, STARTING_CHIPS)

    for username, amount in payouts:
        if amount > 0:
            balance_store.credit(username, amount, reason="settlement")

    config.offchain_settlement = payouts
