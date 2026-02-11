# Backtest Infrastructure

In-process poker bot backtesting. Runs games directly against the `poker.game.Game` engine — no HTTP, no server, ~10-30 games/sec.

## Quick Start

```bash
cd packages/bot
uv run python -m backtest --games 200                            # 4-player, 200 games
uv run python -m backtest --games 100 --bots shark,hawk          # Head-to-head
uv run python -m backtest --games 50 --bots shark,fox --log      # With JSONL hand logs
uv run python -m backtest --games 500 --sims 100                 # Higher equity accuracy
```

## Structure

```
backtest/
├── __main__.py       CLI entry point (--games, --bots, --log, --sims)
├── engine.py         Game runner: run_game() -> GameResult
├── logger.py         JSONL hand-by-hand logger
├── stats.py          Statistical report (wins, win%, h2h matrix, timing)
├── lab.py            Strategy laboratory: dynamic loading, arena, whitelisting
├── workspace/        Agent-created strategies go here during development
│   └── template.py   Minimal strategy skeleton
├── whitelisted/      Approved strategies ready for HTTP play
│   └── __init__.py   Auto-discovers strategies, exports WHITELISTED dict
└── results/          JSONL log output (gitignored)
```

## Key Types

### `GameResult` (engine.py)
```python
@dataclass
class GameResult:
    game_number: int
    winner: str
    hand_count: int
    chip_history: dict[str, list[int]]   # name -> chips after each hand
    hand_logs: list[HandLog]             # only populated with record_hands=True
```

### `HandLog` (engine.py)
```python
@dataclass
class HandLog:
    hand_number: int
    players_cards: dict[str, list[str]]  # name -> ["Ah", "Kd"]
    community_cards: list[str]
    actions: list[dict]                  # [{player, action, amount}, ...]
    winners: list[str]
    pot: int
```

## Engine API

```python
from backtest.engine import run_game, STRATEGIES

# Run with built-in strategies
result = run_game(["Shark", "Hawk"], game_number=1, record_hands=True)

# Run with custom strategies (for the lab)
custom = {"mybot": (decide_fn, reset_fn), "shark": STRATEGIES["shark"]}
result = run_game(["Mybot", "Shark"], game_number=1, strategies=custom)
```

## Lab API (Strategy Laboratory)

```python
from backtest.lab import load_strategy, run_arena, whitelist_strategy

# Load a strategy from any .py file
name, strat = load_strategy("backtest/workspace/my_bot.py")

# Run arena: all strategies play N games
results = run_arena(strategy_map, num_games=200, sims=50)

# Approve and copy to whitelisted/
whitelist_strategy("my_bot", "backtest/workspace/my_bot.py")
```

## Strategy Interface

Every strategy file must export:

```python
def decide(state: dict[str, Any]) -> Decision:
    """Takes game state, returns action."""
    ...

def reset_tracker() -> None:
    """Resets any per-game global state."""
    ...
```

The `Decision` dataclass:
```python
@dataclass(frozen=True)
class Decision:
    action: str              # "check", "fold", "call", "bet", "raise", "all_in"
    amount: int | None       # Required for "bet" and "raise"
    comment: str | None      # Optional table chat
```

## State Dict Reference

| Field | Type | Description |
|-------|------|-------------|
| `phase` | str | `"preflop"`, `"flop"`, `"turn"`, `"river"` |
| `your_cards` | list[str] | `["Ah", "Kd"]` |
| `community_cards` | list[str] | 0-5 cards |
| `pot` | int | Total pot |
| `amount_to_call` | int | 0 = can check |
| `min_raise` | int | Minimum raise total |
| `your_chips` | int | Your stack |
| `players` | list[dict] | `{id, name, chips, current_bet, is_folded, is_all_in}` |
| `dealer` | int | Dealer player ID |
| `hand_number` | int | Current hand |
| `recent_actions` | list[dict] | `{player, action, amount}` (last 10) |
| `is_your_turn` | bool | True when it's your turn |
| `current_turn` | int \| None | Player ID whose turn it is |
| `game_over` | bool | True when the game has ended |
| `winner` | str \| None | Winner's name (only set when game_over) |

## Available Imports

Strategies can import from the `bot` package:

```python
from bot.equity import estimate_equity           # Monte Carlo win probability
from bot.cards import rank_index, is_suited, is_pair, gap, SimDeck
from bot.preflop_ranges import classify_hand, determine_position, preflop_action, HandTier, Position, PreflopAction
from bot.strategies.board import (
    analyze_board, has_flush, has_flush_draw,
    has_open_ended_straight_draw, has_overpair, has_top_pair,
    top_pair_kicker_strength, BoardTexture,
)
from bot.strategies.opponent import OpponentTracker, OpponentProfile
```

## JSONL Log Format

One JSON object per hand when `--log` is used:

```json
{"game":1,"hand":3,"players":{"Shark":["Ah","Kd"],"Hawk":["9c","9h"]},"community":["Ts","7d","2c","Jh","4s"],"actions":[{"player":"Shark","action":"raise","amount":60}],"winners":["Hawk"],"pot":240}
```

Analyze with: `cat results/*.jsonl | python -m json.tool` or `jq 'select(.winners[] == "Shark")'`

## Design Decisions

1. **No existing files modified** — imports from `bot.strategies` and `poker.game` directly
2. **`--sims` flag** monkey-patches `estimate_equity.__defaults__` at startup
3. **sys.path resolution** uses `Path(__file__).resolve()` relative to engine.py (not CWD-dependent)
4. **Custom strategies** via `strategies` parameter on `run_game()` for lab use
