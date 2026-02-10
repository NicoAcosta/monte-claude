# Claude Poker — Codebase Audit Report

**Date:** 2026-02-09
**Reviewers:** 4 independent AI agents (superpowers:code-reviewer, feature-dev:code-reviewer, feature-dev:code-architect, sharp-edges)
**Commit:** `2b749b6` (main)
**Scope:** Full server codebase — logic errors, SOLID/DRY violations, missing tests, architectural concerns, security footguns

---

## Executive Summary

The codebase is well-structured with clean separation of concerns, good service layer extraction, and comprehensive integration tests. The three independent reviewers converged on several shared findings, lending high confidence to those issues.

| Severity | Count |
|----------|-------|
| Critical | 4 |
| High | 8 |
| Medium | 10 |
| Low | 10 |

---

## Critical Issues

### CR-1: State version double-increment on resignation (all 3 reviewers)

**File:** `packages/server/src/poker/game.py:221-235`
**Confidence:** 95% (flagged independently by all 3 agents)

When a player resigns on their turn, `resign()` increments `_state_version` (line 222), then delegates to `do_action("fold")` which increments it again (line 199). This breaks optimistic concurrency — clients using `expected_version` get spurious 409 conflicts.

```python
# Line 221-222
player.resigned = True
self._state_version += 1          # first increment

# Line 233-235
if current_player.id == player_id:
    self.do_action(player_id, "fold", comment="[resigned]")  # second increment inside
```

**Fix:** Only increment once. Either skip the increment in `resign()` when delegating to `do_action()`, or add a flag to prevent the double-count.

---

### CR-2: Off-turn resign skips `_acted_this_round` tracking (2 reviewers)

**File:** `packages/server/src/poker/game.py:237-248`
**Confidence:** 90%

When a player resigns NOT on their turn, the code directly mutates `hand_player.is_folded = True` and calls `_record_action()` — bypassing the `do_action()` pipeline entirely. This means `_mark_acted` / `_reset_acted_for_raise` tracking is never updated. With 3+ active players, the betting round could end prematurely or hang because the resigned player's state in `_acted_this_round` is stale.

**Fix:** Refactor to use a shared internal fold path that properly updates betting round tracking.

---

### CR-3: Non-atomic join + balance debit (2 reviewers)

**File:** `packages/server/src/poker/game_service.py:72-85`
**Confidence:** 85%

Balance is debited FIRST, then game registration occurs. If registration fails, the balance is refunded via `credit()`. But if `credit()` also fails (e.g., DB connection lost), the user permanently loses tokens. The debit and join are not wrapped in a single DB transaction.

```python
balance_store.debit(username, config.buy_in)    # step 1: debit
try:
    player = game.register(username, ...)        # step 2: register
except ValueError:
    balance_store.credit(username, config.buy_in) # step 3: refund (what if this fails?)
    raise
```

**Fix:** Wrap the entire join operation in a single PostgreSQL transaction, or debit after successful registration.

---

### CR-4: `debit(username, 0)` crashes for non-existent users (1 reviewer)

**File:** `packages/server/src/poker/balance_store.py:54-73`
**Confidence:** 85%

If `row is None` and `amount == 0`: `current_amount = 0`, the `current_amount < amount` check passes (0 < 0 is False), the `row is None` check on line 63 is dead code (unreachable when `amount > 0`), and execution falls through to `row[1]` on line 73 which throws `TypeError: 'NoneType' object is not subscriptable`.

The `if row is None` block (lines 63-66) is dead code — it's already handled by the `current_amount < amount` check. But the real bug is the `debit(user, 0)` edge case.

**Fix:** Remove dead code, handle the `row is None` case properly by inserting a row or raising early.

---

## High-Priority Issues

### H-1: `GameConfig` is mutable despite project immutability rules (2 reviewers)

**File:** `packages/server/src/poker/game_config.py`

`GameConfig` is a plain `@dataclass`, not `@dataclass(frozen=True)`. Multiple places mutate it: `escrow_service.py` sets `config.escrow_salt`, `config.escrow_config`, etc. The project CLAUDE.md mandates frozen dataclasses. This should either be made frozen (with mutation via `replace()`) or documented as a justified exception.

---

### H-2: `_buy_in_display` logic duplicated (all 3 reviewers)

**Files:**
- `packages/server/src/poker/game_config.py:27-39` (property)
- `packages/server/src/data_api/app.py:124-136` (standalone function)

Identical formatting logic in two places. If it changes, both must be updated.

**Fix:** Extract to a shared pure function in `poker/` that both consume.

---

### H-3: Store initialization duplicated between APIs (2 reviewers)

**Files:**
- `packages/server/src/game_api/app.py:63-78`
- `packages/server/src/data_api/app.py:40-48`

Both apps instantiate the same stores independently via module-level globals. Same pattern, same pool, same stores.

**Fix:** Extract to a shared `create_stores()` factory or a `StoreRegistry` dataclass.

---

### H-4: No thread safety on Game state (1 reviewer)

**File:** `packages/server/src/poker/game.py`

`Game` has no locking. FastAPI runs sync handlers in a thread pool, so concurrent HTTP requests from different players can interleave reads/writes on `current_hand`, `_state_version`, etc. The `expected_version` check provides *detection* but not *prevention*.

---

### H-5: No cleanup of completed games from `GameManager` (2 reviewers)

**File:** `packages/server/src/poker/game_manager.py`

`_games` and `_configs` grow unboundedly. Completed games are never removed from memory. Over time this leaks memory. Metadata is persisted to PostgreSQL, but in-memory `Game` objects remain forever.

---

### H-6: Spectator response mixes delayed and live data (1 reviewer)

**File:** `packages/server/src/game_api/app.py:456-540`

Spectator sees `previous_hand` (one hand behind) for phase/cards/players, but `timer` and `game_over` reflect the current live state. This creates a confusing mix.

---

### H-7: Account creation TOCTOU race (1 reviewer)

**File:** `packages/server/src/poker/account_store.py:42-53`

SELECT to check username existence and INSERT are not atomic. Two concurrent requests could both pass the SELECT, then one INSERT fails with a raw psycopg constraint violation (500) instead of a clean 400.

**Fix:** Use `INSERT ... ON CONFLICT DO NOTHING RETURNING ...` or catch the constraint error.

---

### H-8: `_build_spectator_response` is 85 lines (1 reviewer)

**File:** `packages/server/src/game_api/app.py:456-540`

Single function handling two branches (previous hand exists vs waiting), duplicating player state mapping logic. Violates SRP.

**Fix:** Break into smaller helpers: `_map_spectator_players()`, `_build_waiting_response()`, `_build_hand_response()`.

---

## Medium-Priority Issues

### M-1: `_setup_started_game` duplicated across 7+ test classes

**File:** `packages/server/tests/test_game_api.py`

The create-game + register-2-accounts + join + start pattern is copy-pasted across TestState, TestAction, TestSpectator, TestActionComments, TestChat, TestTimer, TestReason, TestStreams, TestResign. DRY violation.

**Fix:** Extract to a shared fixture or helper in conftest.

---

### M-2: `game_service.py` accesses private `game._players` (1 reviewer)

**Files:** `game_service.py:124`, `game_manager.py:122`, `game_api/app.py:207,477,489,536`

Encapsulation violation — renaming `_players` would break many files.

**Fix:** Add a public `game.player_names` property.

---

### M-3: `GameMetadata.player_names` is `list[str]` in a frozen dataclass

**File:** `packages/server/src/poker/game_metadata_store.py:20`

`frozen=True` prevents field reassignment, but `list` contents are still mutable. `metadata.player_names.append("Eve")` would succeed.

**Fix:** Use `tuple[str, ...]` instead.

---

### M-4: `_on_game_over` fires `settle_offchain_game` for ALL games

**File:** `packages/server/src/game_api/app.py:158-159`

Called for onchain games too (has an early return, so it's safe but wasteful).

---

### M-5: No `__hash__` on `HandRank` despite custom `__eq__`

**File:** `packages/server/src/poker/evaluator.py:23`

Python makes the class unhashable. Will crash if instances are put in sets/dicts.

---

### M-6: `Counter` imported inside function body

**File:** `packages/server/src/poker/evaluator.py:79`

Minor perf — runs on every 5-card evaluation. Move to top of file.

---

### M-7: `getattr(game.get_player(p.id), 'resigned', False)` pattern

**File:** `packages/server/src/game_api/app.py:393,520`

Defensive programming against a field that always exists. Suggests leaky abstraction between `PlayerInHand` and `RegisteredPlayer`.

---

### M-8: `_who_acts_first` helper duplicated in tests

**File:** `packages/server/tests/test_game_api.py` (TestAction:238, TestReason:680)

Identical implementations in two test classes.

---

### M-9: SQL injection pattern in conftest (safe but bad precedent)

**File:** `packages/server/tests/conftest.py:13`

```python
conn.execute(f"TRUNCATE {table} CASCADE")
```

Table names are hardcoded constants, so currently safe. Use `psycopg.sql.Identifier` instead.

---

### M-10: `_advance_to_showdown` deals community cards even when only 1 player remains

**File:** `packages/server/src/poker/hand.py:213-241`

Wastes deck cards and emits unnecessary events when the hand has a single remaining player.

---

## Low-Priority Issues

| ID | Issue | File |
|----|-------|------|
| L-1 | `RegisteredPlayer` not frozen (mutation justified but undocumented) | `game.py:19-25` |
| L-2 | `PlayerInHand` not frozen (hot path, undocumented exception) | `hand.py:12-20` |
| L-3 | `Stream` dataclass not frozen | `stream.py` |
| L-4 | `create_game` service is a thin pass-through with no added value | `game_service.py:28-49` |
| L-5 | `escrow.py` re-exports `compute_payouts` unnecessarily | `escrow.py:221` |
| L-6 | `_get_game_or_404` uses private naming but is a shared helper | `game_api/app.py:87` |
| L-7 | Spectator `buy_in_display` only set in the `prev is not None` branch | `game_api/app.py:460-538` |
| L-8 | No validation that custom `action_timeout` actually works in-game | test gap |
| L-9 | Hardcoded constants (STARTING_CHIPS, BLINDS, etc.) not configurable | `game.py:12-16` |
| L-10 | No CORS configuration visible in either FastAPI app | deployment concern |

---

## Missing Test Coverage

Flagged by multiple reviewers (deduplicated):

| Area | Missing Scenario |
|------|-----------------|
| Resignation | Off-turn resign with 3+ active players (CR-2) |
| Resignation | `state_version` increment verification after forced fold |
| Resignation | Multiple players resign in same hand |
| Resignation | Immediate chip conservation (before next hand starts) |
| Resignation | Side pot interaction with resigned players |
| Balance | `debit(username, 0)` for non-existent user (CR-4) |
| Balance | Concurrent debit race conditions |
| Game lifecycle | `test_game_over_detection` doesn't assert `game.game_over` |
| Escrow | Funding timeout handling |
| Escrow | Concurrent escrow config generation (idempotency) |
| Timer | 4th extension rejected (limit enforcement) |
| Streams | Commentary permissions, only host can commentate |
| Streams | Orphan streams (no FK to game_metadata) |
| Replay | Handling of `player_resigned` events |
| Payout | `compute_payouts` with `buy_in=0` |

---

## Architectural Concerns

### A-1: In-memory game state with no persistence

`GameManager._games` stores all game state in memory. Server restart loses all active games. `game_metadata` only stores lobby data, not full game state.

### A-2: Event callback system is loosely typed

`event_callback: Callable[[str, dict], None]` — no type safety on event payloads, no event bus, hard to add subscribers.

### A-3: No horizontal scaling path

Each server instance has its own `GameManager`. No shared state mechanism (Redis, etc.) for multi-instance deployment.

---

## Priority Recommendations

### Week 1 (Critical)
1. Fix state version double-increment on resign (CR-1)
2. Fix off-turn resign `_acted_this_round` tracking (CR-2)
3. Make join + debit atomic (CR-3)
4. Fix `debit(0)` crash for non-existent users (CR-4)
5. Add resign edge case tests

### Week 2 (High)
6. Extract shared `_buy_in_display` function (H-2)
7. Extract shared store initialization (H-3)
8. Add game cleanup / TTL to `GameManager` (H-5)
9. Handle account creation race with ON CONFLICT (H-7)

### Backlog (Medium/Low)
10. Extract test helpers to conftest (M-1)
11. Add public `player_names` property to Game (M-2)
12. Use `tuple` for frozen dataclass list fields (M-3)
13. Fill test coverage gaps from the table above

---

## Overall Assessment

**Strengths:**
- Clean separation between game logic (Hand), lifecycle (Game), and API wiring
- Good service layer extraction (game_service, balance_service, escrow_service, settlement_service)
- PostgreSQL row-level locking for balance operations
- Auth pattern with closure/thunk for testability
- Comprehensive integration tests covering the full API surface
- Pure replay module with immutable snapshots
- Escrow/settlement signing tests verify cryptographic correctness

**Key Risks:**
- Resignation logic (CR-1, CR-2) is the most dangerous area — multiple reviewers flagged it
- Non-atomic join (CR-3) can lose user funds
- No thread safety is a deployment concern
- Memory leak from never-cleaned games is a production concern

---

## Appendix: Sharp Edges Audit (Security Footguns)

*Reviewed by: sharp-edges agent — focused on error-prone APIs, dangerous configurations, and misuse-resistant design.*

### SE-1: `_check_timeout()` called from spectator endpoint triggers state mutations [HIGH]

**File:** `game_api/app.py:326,436,546,577,624`

`game._check_timeout()` is called in 5 endpoints: `/state`, `/action`, `/spectator`, `/extend`, `/stream/{id}/data`. Each call can auto-fold the current player. This means **unauthenticated spectator polling can fold a player before their action request arrives**. Worse, the `/extend` endpoint calls `_check_timeout()` BEFORE checking if the extension is valid — if the player is 0.001s past deadline, they're folded before the extension is processed.

**Fix:** Check extensions before timeout. Consider separating timeout checking from read endpoints.

---

### SE-2: Settlement endpoint is unauthenticated [HIGH]

**File:** `game_api/app.py:294-311`

`GET /game/{id}/settlement` has no auth. Anyone knowing the `game_id` can request the admin-signed settlement and submit it on-chain. By design this is a feature ("anyone can submit"), but the settlement is computed from in-memory state — if the server restarts between game-over and settlement retrieval, the data is lost. No persistent cache exists for on-chain settlement data.

---

### SE-3: No rate limiting on registration or game creation [HIGH]

**File:** `game_api/app.py:140-176`

`POST /api/register` and `POST /api/games` have no auth, rate limiting, or CAPTCHA. An attacker can create unlimited accounts and games, filling `GameManager._games` until the server OOMs.

---

### SE-4: Resignation can destroy a newly-started hand [HIGH]

**File:** `game.py:206-262`

When a resigning player IS the current turn holder and their fold causes the hand to complete, `_finish_hand()` may call `_start_new_hand()`. Then `resign()` continues and may set `current_hand = None` (line 260), destroying the hand that was just started. This only happens if `alive_players <= 1` after the resign, but the interaction between `do_action` → `_finish_hand` → `_start_new_hand` and the subsequent `resign()` continuation is fragile.

---

### SE-5: `STARTING_CHIPS` coupling between game and settlement [HIGH]

**File:** `escrow_service.py:143`

`compute_payouts(player_chips, config.buy_in, STARTING_CHIPS)` uses the module-level constant `STARTING_CHIPS = 1000`. If this ever becomes configurable per-game, the settlement math breaks and the Escrow contract reverts with `PayoutSumMismatch`, locking funds until expiry.

---

### SE-6: `StreamStore.create()` catches all exceptions as "duplicate" [MEDIUM]

**File:** `stream_store.py:37-39`

Bare `except Exception` catches DB connection errors, syntax errors, etc. and converts them all to "User already has a stream". Production debugging would be difficult.

---

### SE-7: Deck uses Mersenne Twister (not cryptographically secure) [MEDIUM]

**File:** `deck.py:48`

`random.Random(seed)` is predictable after ~624 observed outputs. A sophisticated attacker observing dealt cards via the spectator endpoint (which shows cards after each hand) could predict future hands after ~70 hands. Low risk for a demo project, critical for real-money play.

---

### SE-8: `ActionRequest.action` accepts any string [LOW]

**File:** `models.py:64`

`action: str` accepts `"bluff"`, `"cheat"`, etc. — they fail deeper in the stack but bypass Pydantic validation. Should be `Literal["fold", "check", "call", "bet", "raise", "all_in"]`.

---

### SE-9: Escrow `settle()` callable during FUNDING state [MEDIUM]

**File:** `Escrow.sol:204-235`

The contract allows settlement from FUNDING state (intentional for early settlement). But if the Python server computes payouts based on game chip counts (assuming all deposits), while only partial deposits exist, the contract reverts with `PayoutSumMismatch`. The API guards against this, but direct contract interaction could exploit a compromised admin key.

---

### SE-10: Payout rounding dust assignment differs between onchain/offchain [MEDIUM]

**File:** `payout.py:36-39`

Rounding dust goes to the player with the largest payout. In offchain settlement, keys are usernames (insertion order from `_players`). In onchain settlement, keys are wallet addresses (different insertion order). Tie-breaking could differ between the two, causing 1 unit of dust mismatch and potential `PayoutSumMismatch` revert.

---

### Informational

- **Fee-on-transfer tokens:** `Escrow.deposit()` has a balance check that rejects them. Safe but undocumented.
- **`EscrowFactory._computeSalt`** uses `abi.encodePacked` on fixed-size addresses — safe, no collision risk.
- **`_extra_time` accumulation:** A player can use all 3 extensions at once for `3 * 30 = 90` extra seconds. By design but undocumented.
- **No CORS middleware:** Neither FastAPI app configures CORS, which will block browser-based clients.
