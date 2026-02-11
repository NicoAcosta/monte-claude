# Strategy Lab

Develop winning poker bot strategies through iterative backtesting and multi-agent refinement. Each agent creates a strategy, backtests it against opponents, analyzes results, and refines until convergence. Approved strategies are whitelisted for live HTTP play.

## Overview

You are the **lab orchestrator**. You will spawn multiple Claude agents — each is a "strategy developer" responsible for one bot. The loop is:

1. **Create** — Each agent writes a strategy in `backtest/workspace/`
2. **Backtest** — Run all strategies in the arena (N games)
3. **Analyze** — Study results, opponent patterns, and hand logs
4. **Refine** — Each agent improves their strategy based on data
5. **Converge** — Repeat until win rates stabilize
6. **Approve** — Each agent votes to approve or reject their strategy
7. **Whitelist** — Approved strategies are copied to `backtest/whitelisted/`, ready for HTTP play

## Working Directory

All commands run from `packages/bot/`. The backtest infrastructure is at `packages/bot/backtest/`.

## Phase 1: Setup

### Ask the user

Use AskUserQuestion:
- **How many agents?** (2-4 recommended, each develops one strategy)
- **Include built-in bots as opponents?** (Shark, Wolf, Fox, Hawk — recommended for calibration)
- **Games per round?** (100-200 for iteration, 500+ for final validation)
- **Convergence threshold?** (e.g., "stop when no strategy changes win rate by more than 3% between rounds")

### Understand the existing strategies

Before creating anything, read the existing strategies to understand what works:

```
packages/bot/bot/strategies/shark.py   — GTO-inspired adaptive (opponent modeling + board texture)
packages/bot/bot/strategies/wolf.py    — Hyper-aggressive LAG (constant pressure, big bluffs)
packages/bot/bot/strategies/fox.py     — Deceptive tricky (traps, slow-plays, image manipulation)
packages/bot/bot/strategies/hawk.py    — Mathematically optimal TAG (pot odds, Kelly criterion, SPR)
```

Also read:
```
packages/bot/bot/strategies/opponent.py   — OpponentTracker, OpponentProfile
packages/bot/bot/strategies/board.py      — Board texture analysis
packages/bot/bot/equity.py                — Monte Carlo equity estimation
packages/bot/bot/preflop_ranges.py        — Hand classification and position ranges
packages/bot/backtest/BACKTEST.md         — Full API reference
packages/bot/backtest/workspace/template.py — Strategy skeleton
```

## Phase 2: Strategy Creation

For each agent, spawn a Task (subagent_type: general-purpose) with this prompt structure:

```
You are a poker strategy developer. Your job is to create a winning poker bot strategy.

IDENTITY: You are developing the "{name}" strategy.

GOAL: Beat the other strategies through {specific_angle}. Examples of angles:
- Exploit-heavy: track opponents aggressively, find and punish leaks
- GTO-balanced: make unexploitable decisions using Nash equilibrium concepts
- Adaptive pressure: adjust aggression dynamically based on stack depths and opponent tendencies
- Trap specialist: induce bluffs and overbets, maximize value with deception
- Mathematical edge: pure EV calculations, Kelly sizing, reverse implied odds

CONSTRAINTS:
- File: packages/bot/backtest/workspace/{name}.py
- Must define: decide(state) -> Decision and reset_tracker() -> None
- Copy the template from packages/bot/backtest/workspace/template.py as your starting point
- Use the available imports (see template docstring for full list)

ALGORITHMIC ADVANTAGES TO LEVERAGE:
1. OpponentTracker — tracks VPIP, PFR, aggression factor, fold-to-raise per opponent
   - Access via: _tracker.profile("OpponentName") -> OpponentProfile
   - .vpip, .pfr, .aggression_factor, .fold_to_raise_pct, .is_passive, .is_aggressive, .is_tight, .is_loose
2. Board texture — analyze_board() returns wet/dry, flush/straight draws, paired boards
3. Equity estimation — estimate_equity(hole, community, num_opponents) for win probability
4. Preflop ranges — classify_hand() for tier (Premium/Strong/Playable/Marginal/Trash)
5. Position awareness — determine_position() for Early/Middle/Late/Blind
6. Dynamic adaptation — adjust thresholds based on opponent profiles across hands
7. Stack-to-pot ratio (SPR) — commit/fold decisions based on effective stacks vs pot
8. Hand history — use recent_actions to detect opponent patterns within a hand

STRATEGY DESIGN TIPS:
- The default equity sims are 50 (fast but noisy). Design around this variance.
- Opponents track YOUR patterns too. Don't be predictable — mix in occasional bluffs.
- Position is king in poker. Late position should play more hands, more aggressively.
- Against passive opponents: value bet thin, don't bluff much.
- Against aggressive opponents: trap more, call down lighter, let them hang themselves.
- Bet sizing matters: big bets fold out draws, small bets keep worse hands in.
- Don't overcommit with marginal hands. Pot control on medium-strength holdings.

Write the complete strategy file now.
```

**Launch all agents in parallel** (multiple Task tool calls in one message) for speed.

## Phase 3: Backtest (Arena)

After all agents finish writing their strategies, run the arena:

```bash
cd packages/bot

# Verify strategies load (quick sanity check)
uv run python -c "
from backtest.lab import discover_workspace
ws = discover_workspace()
print(f'Loaded {len(ws)} workspace strategies: {list(ws.keys())}')
"

# Run arena with workspace strategies + built-in opponents
uv run python -c "
from backtest.lab import build_arena_strategies, run_arena
arena = build_arena_strategies(include_builtin=['shark', 'hawk'])
results = run_arena(arena, num_games=200)
"
```

Or run with JSONL logging for deep analysis:

```bash
uv run python -c "
from backtest.lab import build_arena_strategies, run_arena
from backtest.logger import BacktestLogger
arena = build_arena_strategies(include_builtin=['shark', 'hawk'])
bot_names = [n.capitalize() for n in arena]
logger = BacktestLogger(bot_names)
results = run_arena(arena, num_games=200, record_hands=True)
for r in results:
    logger.log_game(r)
logger.close()
print(f'Logs: {logger.path}')
"
```

## Phase 4: Analysis

After the backtest, analyze results for each agent. Spawn analysis agents in parallel:

For each strategy developer agent, provide:
1. **The full arena results** (win rates, h2h matrix, avg hands survived, avg chip delta)
2. **Their strategy's specific weaknesses** — extract from hand logs:
   - Hands where they lost big pots (pot > 200)
   - Hands where they folded to bluffs (opponents won without showdown)
   - Hands where they called too much (lost at showdown with weak hands)
3. **Opponent tendencies** they should exploit

Example analysis (run via bash to extract from JSONL):

```bash
# Find hands where a specific bot lost big pots
cat backtest/results/*.jsonl | python3 -c "
import json, sys
for line in sys.stdin:
    h = json.loads(line)
    if h['pot'] > 200 and 'BotName' not in h.get('winners', []):
        print(json.dumps(h, indent=2))
" | head -100
```

## Phase 5: Refinement

Spawn each strategy agent again with their analysis data:

```
You are refining the "{name}" strategy.

PREVIOUS RESULTS:
{paste win rates, h2h matrix}

WEAKNESSES IDENTIFIED:
{paste specific hand examples and patterns}

OPPONENT TENDENCIES:
{paste opponent profiles from the arena data}

INSTRUCTIONS:
- Read your current strategy: packages/bot/backtest/workspace/{name}.py
- Identify and fix the specific weaknesses above
- Do NOT rewrite from scratch — make targeted improvements
- Focus on the highest-impact changes first
- Consider adding/improving:
  - Opponent-specific adjustments (e.g., "if opponent is loose-passive, value bet thinner")
  - Board texture reads (e.g., "on monotone boards, check-raise more with flushes")
  - Bet sizing tells (e.g., "opponents who min-raise are usually weak")
  - Stack depth awareness (e.g., "with SPR < 3, commit or fold")

Update the strategy file with your improvements.
```

## Phase 6: Convergence Check

After each refinement round, re-run the arena and compare results:

```python
# Track win rates across rounds
round_1_results = {bot: win_pct for bot, stats in summary.items()}
round_2_results = {bot: win_pct for bot, stats in summary.items()}

# Check if any strategy changed by more than threshold
max_delta = max(abs(round_2_results[b] - round_1_results[b]) for b in bots)
converged = max_delta < convergence_threshold  # e.g., 3%
```

**Convergence criteria** (stop iterating when ALL are true):
- No strategy's win rate changed by more than the threshold between rounds
- At least 2 rounds have been completed
- No strategy has a win rate below 15% (degenerate strategy detection)

If not converged, go back to Phase 4.

## Phase 7: Final Validation

Run a large final backtest (500+ games) for statistical confidence:

```bash
uv run python -c "
from backtest.lab import build_arena_strategies, run_arena
arena = build_arena_strategies(include_builtin=['shark', 'wolf', 'fox', 'hawk'])
results = run_arena(arena, num_games=500, record_hands=True)
"
```

## Phase 8: Approval Vote

For each strategy, ask the developing agent to vote:

```
Review your final results for "{name}":

Win rate: {X}%
H2H vs Shark: {X}%
H2H vs Hawk: {X}%
Avg chip delta: {X}

Do you APPROVE this strategy for whitelisting?
- APPROVE: Strategy is competitive, handles edge cases, has positive EV
- REJECT: Strategy has fundamental flaws that need more iteration

Provide your vote and a 2-sentence justification.
```

**Approval threshold**: A strategy is approved if:
- Its developer votes APPROVE
- Win rate is above 20% in the final validation (not degenerate)
- It doesn't crash on any game in the final run

## Phase 9: Whitelist

For each approved strategy:

```bash
uv run python -c "
from backtest.lab import whitelist_strategy
whitelist_strategy('{name}', 'backtest/workspace/{name}.py')
"
```

Then verify the whitelisted strategy works with the HTTP client interface:

```bash
uv run python -c "
from backtest.whitelisted import WHITELISTED
print('Whitelisted strategies:', list(WHITELISTED.keys()))
for name, (decide_fn, reset_fn) in WHITELISTED.items():
    reset_fn()
    print(f'  {name}: decide={decide_fn.__module__}, reset OK')
"
```

### Making whitelisted strategies available for HTTP play

The whitelisted strategies are self-contained .py files in `backtest/whitelisted/`. To use one in a live HTTP game:

```bash
# Option A: Run directly with the bot client
uv run python -c "
import asyncio
from bot.client import Client
from backtest.whitelisted import WHITELISTED

async def play():
    decide_fn, reset_fn = WHITELISTED['{name}']
    reset_fn()
    client = Client('http://localhost:8001')
    # ... join game and play using decide_fn(state)

asyncio.run(play())
"

# Option B: Register in STRATEGIES dict temporarily
uv run python -c "
from bot.strategies import STRATEGIES
from backtest.whitelisted import WHITELISTED
STRATEGIES.update(WHITELISTED)
# Now 'python -m bot --strategy {name}' works
"
```

## Output Summary

When the lab completes, print a final summary:

```
============================================================
  STRATEGY LAB COMPLETE
============================================================

  Rounds: {N}
  Games per round: {N}
  Final validation: {N} games

  Results:
    {name1}: {win%} — APPROVED ✓ → whitelisted/{name1}.py
    {name2}: {win%} — APPROVED ✓ → whitelisted/{name2}.py
    {name3}: {win%} — REJECTED ✗ (reason)

  Whitelisted strategies ready at:
    packages/bot/backtest/whitelisted/

============================================================
```

## Key Principles

1. **Data-driven refinement**: Never guess — always backtest before and after changes
2. **Exploit, don't just survive**: The best strategies find and punish opponent weaknesses
3. **Algorithmic edges matter**: Opponent tracking, board analysis, and equity calculation are your weapons
4. **Convergence over perfection**: Stop when returns are diminishing, not when "perfect"
5. **The meta-game**: If all opponents are tight, the optimal strategy is loose. Adaptation wins.
