"""Monte Carlo equity calculator using phevaluator."""

from __future__ import annotations

import random

from phevaluator import evaluate_cards

from .cards import SimDeck


def estimate_equity(
    hole: tuple[str, str],
    community: tuple[str, ...],
    num_opponents: int,
    num_simulations: int = 50,
    seed: int | None = None,
) -> float:
    """Estimate win probability via Monte Carlo simulation.

    Returns equity as float 0.0–1.0 (fraction of simulations won or tied).
    phevaluator: lower rank = stronger hand.
    """
    if num_opponents < 1:
        return 1.0

    rng = random.Random(seed)
    known = (*hole, *community)
    cards_to_deal = 5 - len(community)
    wins = 0.0

    for _ in range(num_simulations):
        deck = SimDeck(exclude=known, rng=rng)

        # Deal remaining community cards
        sim_community = list(community) + deck.deal(cards_to_deal)

        # Evaluate our hand (7 cards)
        our_rank = evaluate_cards(*hole, *sim_community)

        # Deal and evaluate each opponent
        best_opp = our_rank + 1  # Worse than ours by default
        for _ in range(num_opponents):
            opp_hole = deck.deal(2)
            opp_rank = evaluate_cards(*opp_hole, *sim_community)
            if opp_rank < best_opp:
                best_opp = opp_rank

        # Lower rank = stronger. Count ties as half a win.
        if our_rank < best_opp:
            wins += 1.0
        elif our_rank == best_opp:
            wins += 0.5

    return wins / num_simulations
