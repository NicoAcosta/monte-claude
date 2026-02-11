"""Statistical analysis and report generation for backtest results."""

from __future__ import annotations

import math

from .engine import GameResult


def print_report(
    results: list[GameResult],
    bot_names: list[str],
    elapsed: float,
) -> None:
    """Print a full statistical report to stdout."""
    n = len(results)
    if n == 0:
        print("No games played.")
        return

    # --- Per-bot stats ---
    wins: dict[str, int] = {b: 0 for b in bot_names}
    hands_survived: dict[str, list[int]] = {b: [] for b in bot_names}
    chip_deltas: dict[str, list[int]] = {b: [] for b in bot_names}

    starting_chips = 1000  # default poker starting stack

    for r in results:
        # Count wins
        for b in bot_names:
            if b.lower() in r.winner.lower():
                wins[b] += 1

        # Hands survived = how many chip snapshots before going to 0
        for b in bot_names:
            history = r.chip_history.get(b, [])
            survived = len(history)
            for i, chips in enumerate(history):
                if chips == 0:
                    survived = i + 1
                    break
            hands_survived[b].append(survived)

            # Chip delta = final chips minus starting
            final = history[-1] if history else 0
            chip_deltas[b].append(final - starting_chips)

    print()
    print("=" * 66)
    print(f"  BACKTEST REPORT — {n} games, {len(bot_names)} players")
    print("=" * 66)
    print()

    # Win table
    header = f"  {'Bot':<10} {'Wins':>6} {'Win%':>7} {'Avg Hands':>10} {'Avg Δ Chips':>12}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for b in bot_names:
        w = wins[b]
        pct = 100 * w / n
        avg_h = _mean(hands_survived[b])
        avg_d = _mean(chip_deltas[b])
        print(f"  {b:<10} {w:>6} {pct:>6.1f}% {avg_h:>10.1f} {avg_d:>+12.0f}")

    # --- Head-to-head matrix (only with 3+ bots) ---
    if len(bot_names) >= 3:
        print()
        print("  Head-to-Head Win Rates:")
        print()

        # Count how many games each bot won against each other bot
        h2h: dict[str, dict[str, int]] = {
            a: {b: 0 for b in bot_names} for a in bot_names
        }
        for r in results:
            winner = None
            for b in bot_names:
                if b.lower() in r.winner.lower():
                    winner = b
                    break
            if winner:
                for b in bot_names:
                    if b != winner:
                        h2h[winner][b] += 1

        # Print matrix
        col_w = 8
        print("  " + " " * 10 + "".join(f"{b:>{col_w}}" for b in bot_names))
        for a in bot_names:
            row = f"  {a:<10}"
            for b in bot_names:
                if a == b:
                    row += f"{'---':>{col_w}}"
                else:
                    total = h2h[a][b] + h2h[b][a]
                    if total > 0:
                        rate = 100 * h2h[a][b] / total
                        row += f"{rate:>{col_w - 1}.0f}%"
                    else:
                        row += f"{'n/a':>{col_w}}"
            print(row)

    # --- Timing ---
    print()
    print("  " + "-" * 40)
    gps = n / elapsed if elapsed > 0 else 0
    total_hands = sum(r.hand_count for r in results)
    print(f"  Time: {elapsed:.1f}s | {gps:.1f} games/sec | {total_hands} total hands")
    print("=" * 66)
    print()


def _mean(values: list[int | float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
