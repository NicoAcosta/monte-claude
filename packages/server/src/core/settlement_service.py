"""Off-chain settlement — compute payouts and credit balances."""

from __future__ import annotations

from core.balance_store import BalanceStore
from core.game_protocol import GameProtocol
from core.game_config import GameConfig
from core.game_mode import GameMode
from core.payout import compute_payouts


def settle_offchain_game(
    game: GameProtocol,
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

    player_chips: dict[str, int] = {p.name: p.chips for p in game.players}
    payouts = compute_payouts(player_chips, config.buy_in, game.starting_chips)

    for username, amount in payouts:
        if amount > 0:
            balance_store.credit(username, amount, reason="settlement")

    config.offchain_settlement = payouts
