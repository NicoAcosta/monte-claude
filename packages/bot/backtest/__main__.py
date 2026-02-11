"""CLI entry point: uv run python -m backtest [options]"""

from __future__ import annotations

import argparse
import sys
import time

from .engine import run_game, STRATEGIES
from .logger import BacktestLogger
from .stats import print_report

ALL_BOTS = [name.capitalize() for name in STRATEGIES]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="backtest",
        description="Run poker bot backtests",
    )
    parser.add_argument(
        "--games", type=int, default=200,
        help="Number of games to simulate (default: 200)",
    )
    parser.add_argument(
        "--bots", type=str, default=",".join(ALL_BOTS),
        help="Comma-separated bot names (default: all 4)",
    )
    parser.add_argument(
        "--log", action="store_true",
        help="Enable JSONL hand-by-hand logging to backtest/results/",
    )
    parser.add_argument(
        "--sims", type=int, default=None,
        help="Monte Carlo simulations per equity estimate (default: 50)",
    )
    args = parser.parse_args()

    # Parse and validate bot names
    bot_names = [b.strip().capitalize() for b in args.bots.split(",")]
    if len(bot_names) < 2:
        print(f"Error: need at least 2 bots, got {len(bot_names)}", file=sys.stderr)
        sys.exit(1)

    for b in bot_names:
        if b.lower() not in STRATEGIES:
            valid = ", ".join(ALL_BOTS)
            print(f"Error: unknown bot '{b}'. Valid: {valid}", file=sys.stderr)
            sys.exit(1)

    # Monkey-patch Monte Carlo simulation count if requested
    if args.sims is not None:
        from bot.equity import estimate_equity

        # estimate_equity(hole, community, num_opponents, num_simulations=50, seed=None)
        # __defaults__ = (50, None)
        estimate_equity.__defaults__ = (args.sims, None)

    num_games = args.games
    record_hands = args.log

    # Set up logger
    logger = BacktestLogger(bot_names) if record_hands else None

    print()
    print("=" * 60)
    sims_info = f", sims={args.sims}" if args.sims else ""
    print(f"  BACKTEST: {' vs '.join(bot_names)} ({num_games} games{sims_info})")
    print("=" * 60)

    results = []
    t0 = time.time()
    progress_step = max(1, num_games // 10)

    for i in range(1, num_games + 1):
        result = run_game(bot_names, game_number=i, record_hands=record_hands)
        results.append(result)

        if logger:
            logger.log_game(result)

        if i % progress_step == 0 or i == num_games:
            elapsed = time.time() - t0
            wins = {}
            for b in bot_names:
                wins[b] = sum(
                    1 for r in results if r.winner.lower() == b.lower()
                )
            score = " | ".join(f"{b} {wins[b]}" for b in bot_names)
            pct = 100 * i / num_games
            print(f"  [{pct:5.1f}%] Game {i:>4}/{num_games} ({elapsed:5.1f}s) | {score}")

    elapsed = time.time() - t0

    if logger:
        logger.close()
        print(f"\n  Logs written to: {logger.path}")

    print_report(results, bot_names, elapsed)


if __name__ == "__main__":
    main()
