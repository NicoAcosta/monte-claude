"""Strategy laboratory: dynamic loading, arena backtesting, and whitelisting."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import time
from pathlib import Path
from typing import Callable

from .engine import GameResult, run_game, STRATEGIES
from .stats import print_report

WORKSPACE_DIR = Path(__file__).resolve().parent / "workspace"
WHITELISTED_DIR = Path(__file__).resolve().parent / "whitelisted"


# ---------------------------------------------------------------------------
# Dynamic strategy loading
# ---------------------------------------------------------------------------

def load_strategy(filepath: str | Path) -> tuple[str, tuple[Callable, Callable]]:
    """Dynamically load a strategy from a .py file.

    The file must define decide(state) -> Decision and reset_tracker() -> None.
    Returns (name, (decide_fn, reset_fn)).
    """
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Strategy file not found: {path}")

    name = path.stem  # e.g. "my_bot" from "my_bot.py"
    mod_name = f"strategy_{name}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules so @dataclass can resolve the module (Python 3.13+)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "decide"):
        raise AttributeError(f"Strategy {name} missing decide(state) function")
    if not hasattr(module, "reset_tracker"):
        raise AttributeError(f"Strategy {name} missing reset_tracker() function")

    return name, (module.decide, module.reset_tracker)


def discover_workspace() -> dict[str, tuple[Callable, Callable]]:
    """Load all strategy files from the workspace/ directory.

    Returns dict like STRATEGIES: {name_lower: (decide_fn, reset_fn)}.
    Skips template.py and __init__.py.
    """
    found: dict[str, tuple[Callable, Callable]] = {}
    if not WORKSPACE_DIR.exists():
        return found

    for path in sorted(WORKSPACE_DIR.glob("*.py")):
        if path.name in ("template.py", "__init__.py"):
            continue
        try:
            name, strat = load_strategy(path)
            found[name.lower()] = strat
        except Exception as e:
            print(f"  [warn] Skipping {path.name}: {e}")

    return found


# ---------------------------------------------------------------------------
# Arena: round-robin backtesting
# ---------------------------------------------------------------------------

def build_arena_strategies(
    workspace_names: list[str] | None = None,
    include_builtin: list[str] | None = None,
) -> dict[str, tuple[Callable, Callable]]:
    """Build a merged strategy dict for the arena.

    workspace_names: specific workspace strategies to include (None = all).
    include_builtin: built-in strategies to include (None = none).
    """
    arena: dict[str, tuple[Callable, Callable]] = {}

    # Load workspace strategies
    ws = discover_workspace()
    if workspace_names is not None:
        for name in workspace_names:
            key = name.lower()
            if key in ws:
                arena[key] = ws[key]
            else:
                print(f"  [warn] Workspace strategy '{name}' not found")
    else:
        arena.update(ws)

    # Include built-in strategies
    if include_builtin:
        for name in include_builtin:
            key = name.lower()
            if key in STRATEGIES:
                arena[key] = STRATEGIES[key]
            else:
                print(f"  [warn] Built-in strategy '{name}' not found")

    return arena


def run_arena(
    strategy_map: dict[str, tuple[Callable, Callable]],
    num_games: int = 200,
    sims: int | None = None,
    record_hands: bool = False,
) -> list[GameResult]:
    """Run an arena: all strategies play num_games against each other.

    Returns list of GameResult.
    """
    if len(strategy_map) < 2:
        print("  [error] Need at least 2 strategies for the arena")
        return []

    # Apply sims override
    if sims is not None:
        from bot.equity import estimate_equity
        estimate_equity.__defaults__ = (sims, None)

    # Capitalize names for display (game engine uses these as player names)
    bot_names = [name.capitalize() for name in strategy_map]
    # Build strategies dict with capitalized-then-lowered keys (matching engine lookup)
    strats = {name.lower(): strategy_map[name.lower()] for name in bot_names}

    print()
    print("=" * 60)
    print(f"  ARENA: {' vs '.join(bot_names)} ({num_games} games)")
    print("=" * 60)

    results: list[GameResult] = []
    t0 = time.time()
    progress_step = max(1, num_games // 10)

    for i in range(1, num_games + 1):
        result = run_game(
            bot_names,
            game_number=i,
            record_hands=record_hands,
            strategies=strats,
        )
        results.append(result)

        if i % progress_step == 0 or i == num_games:
            elapsed = time.time() - t0
            wins = {}
            for b in bot_names:
                wins[b] = sum(1 for r in results if b.lower() in r.winner.lower())
            score = " | ".join(f"{b} {wins[b]}" for b in bot_names)
            pct = 100 * i / num_games
            print(f"  [{pct:5.1f}%] Game {i:>4}/{num_games} ({elapsed:5.1f}s) | {score}")

    elapsed = time.time() - t0
    print_report(results, bot_names, elapsed)
    return results


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def summarize_results(
    results: list[GameResult],
    bot_names: list[str],
) -> dict[str, dict]:
    """Extract per-bot summary stats from arena results.

    Returns {name: {wins, win_pct, avg_hands, avg_chip_delta}}.
    """
    n = len(results)
    if n == 0:
        return {}

    summary: dict[str, dict] = {}
    for b in bot_names:
        wins = sum(1 for r in results if b.lower() in r.winner.lower())
        hands = []
        deltas = []
        for r in results:
            history = r.chip_history.get(b, [])
            survived = len(history)
            for i, chips in enumerate(history):
                if chips == 0:
                    survived = i + 1
                    break
            hands.append(survived)
            final = history[-1] if history else 0
            deltas.append(final - 1000)

        summary[b] = {
            "wins": wins,
            "win_pct": 100 * wins / n if n > 0 else 0,
            "avg_hands": sum(hands) / len(hands) if hands else 0,
            "avg_chip_delta": sum(deltas) / len(deltas) if deltas else 0,
        }
    return summary


# ---------------------------------------------------------------------------
# Whitelisting: promote strategy to production-ready
# ---------------------------------------------------------------------------

def whitelist_strategy(name: str, source_path: str | Path) -> Path:
    """Copy a strategy file to whitelisted/, ready for HTTP play.

    Returns the destination path.
    """
    src = Path(source_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Source strategy not found: {src}")

    WHITELISTED_DIR.mkdir(exist_ok=True)
    dest = WHITELISTED_DIR / f"{name.lower()}.py"
    shutil.copy2(src, dest)
    print(f"  Whitelisted: {name} -> {dest}")
    return dest


def list_whitelisted() -> list[str]:
    """List all whitelisted strategy names."""
    if not WHITELISTED_DIR.exists():
        return []
    return sorted(
        p.stem for p in WHITELISTED_DIR.glob("*.py")
        if p.name != "__init__.py"
    )
