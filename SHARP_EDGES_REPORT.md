# Sharp Edges Analysis Report

**Date:** 2025-02-08
**Scope:** Full codebase — `packages/server/src/poker/` (Python) + `packages/contracts/src/` (Solidity)
**Methodology:** Three-adversary model (Scoundrel, Lazy Developer, Confused Developer), zero/empty/null edge case probing

---

## Validation Summary

| # | Finding | Severity | Verdict | Fix Effort |
|---|---------|----------|---------|------------|
| 1 | Unauthenticated player state | CRITICAL | CONFIRMED | Low |
| 2 | Escrow env var defaults | CRITICAL→MEDIUM | PARTIALLY CONFIRMED | Low |
| 3 | Balance store concurrency | HIGH | CONFIRMED | Medium |
| 4 | Pydantic validation gaps | HIGH→MEDIUM | PARTIALLY CONFIRMED | Low |
| 5 | 100% rake valid (Solidity) | HIGH | CONFIRMED | Trivial |
| 6 | Empty payouts array (Solidity) | MEDIUM→LOW | PARTIALLY CONFIRMED | Trivial |
| 7 | `address(0)` participant (Solidity) | MEDIUM | CONFIRMED | Trivial |
| 8 | Wallet address not validated | MEDIUM | CONFIRMED | Low |
| 9 | Division by zero in `compute_payouts()` | MEDIUM→LOW | PARTIALLY CONFIRMED | Trivial |
| 10 | No rate limiting | HIGH | CONFIRMED | Medium |

---

## Finding 1: Unauthenticated Player State Access

**Severity:** CRITICAL
**Verdict:** CONFIRMED

### Description

`GET /game/{game_id}/state/{player_id}` has zero authentication. Anyone can view any player's hole cards by guessing sequential player IDs (1, 2, 3...).

### Evidence

`packages/server/src/poker/server.py` — the state endpoint:

```python
@app.get("/game/{game_id}/state/{player_id}", response_model=PlayerStateResponse)
def state(game_id: int, player_id: int):
    game = _get_game_or_404(game_id)
    rp = game.get_player(player_id)
    # ... returns hole cards, no auth check
```

Compare to every other sensitive endpoint which uses `Depends(require_auth)`. The `PlayerStateResponse` model includes `your_cards: list[str]` (hole cards). Player IDs are sequential starting at 1 and revealed by the unauthenticated `/waiting` endpoint.

### Proposed Fix

**File:** `packages/server/src/poker/server.py`

```python
# BEFORE:
@app.get("/game/{game_id}/state/{player_id}", response_model=PlayerStateResponse)
def state(game_id: int, player_id: int):
    game = _get_game_or_404(game_id)
    rp = game.get_player(player_id)
    if rp is None:
        raise HTTPException(status_code=404, detail="Player not found")

# AFTER:
@app.get("/game/{game_id}/state/{player_id}", response_model=PlayerStateResponse)
def state(game_id: int, player_id: int, account: Account = Depends(require_auth)):
    game = _get_game_or_404(game_id)
    rp = game.get_player(player_id)
    if rp is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if rp.name != account.username:
        raise HTTPException(status_code=403, detail="Cannot view other players' cards")
```

**New tests:**

```python
def test_state_requires_auth(client):
    game_id = create_game(client)
    resp = client.get(f"/game/{game_id}/state/1")
    assert resp.status_code == 401

def test_state_cannot_view_other_player(client):
    # Alice tries to view Bob's state → 403
```

**Blast radius:** All clients polling state must now send `X-API-Key` header.

---

## Finding 2: Escrow Environment Variable Defaults

**Severity:** MEDIUM (downgraded from CRITICAL)
**Verdict:** PARTIALLY CONFIRMED

### Description

`get_env_config()` defaults critical variables to empty strings. Originally claimed "no startup validation" — but runtime checks DO exist at the point of use in `server.py`.

### Evidence

`packages/server/src/poker/escrow.py`:

```python
def get_env_config() -> dict:
    return {
        "server_private_key": os.environ.get("SERVER_PRIVATE_KEY", ""),  # empty default
        "base_rpc_url": os.environ.get("BASE_RPC_URL", "http://localhost:8545"),  # localhost default
        "factory_address": os.environ.get("FACTORY_ADDRESS", ""),  # empty default
        ...
    }
```

**However**, `server.py` does check before use:

```python
if not server_addr:
    raise HTTPException(status_code=500, detail="Server private key not configured")
if not env["factory_address"]:
    raise HTTPException(status_code=500, detail="Factory address not configured")
```

**What's still a real concern:**
- No fail-fast at startup (fails only when a user hits an escrow endpoint)
- `BASE_RPC_URL` defaults to localhost with no validation
- Error messages leak config details to end users

### Proposed Fix

**File:** `packages/server/src/poker/escrow.py`

```python
# Add validation mode:
def get_env_config(*, validate: bool = False) -> dict:
    cfg = {
        "server_private_key": os.environ.get("SERVER_PRIVATE_KEY", ""),
        "base_rpc_url": os.environ.get("BASE_RPC_URL", "http://localhost:8545"),
        ...
    }
    if validate:
        missing = []
        if not cfg["server_private_key"]:
            missing.append("SERVER_PRIVATE_KEY")
        if not cfg["factory_address"]:
            missing.append("FACTORY_ADDRESS")
        if missing:
            raise ValueError(f"Missing required env vars for on-chain escrow: {', '.join(missing)}")
    return cfg
```

Then call `get_env_config(validate=True)` in escrow endpoints.

**Blast radius:** On-chain games fail fast with clear error. Free/offchain games unaffected.

---

## Finding 3: Balance Store Concurrency

**Severity:** HIGH
**Verdict:** CONFIRMED

### Description

`balance_store.py` has no file locking and no atomic writes. FastAPI dispatches sync handlers to a thread pool, so concurrent requests can corrupt the CSV or double-spend.

### Evidence

`packages/server/src/poker/balance_store.py` — `_rewrite()`:

```python
def _rewrite(self) -> None:
    with open(self._csv_path, "w", newline="") as f:  # truncate + write, not atomic
        writer = csv.writer(f)
        writer.writerow(self._CSV_HEADERS)
        for bal in self._balances.values():
            writer.writerow((bal.username, bal.amount, bal.last_claim_at))
```

No `fcntl`, no `threading.Lock`, no temp-file-then-rename. The `debit()` method has a classic TOCTOU race: check balance → compute new balance → write. Two concurrent debits can both pass the check before either writes.

### Proposed Fix

**File:** `packages/server/src/poker/balance_store.py`

```python
import threading
import tempfile
import os

class BalanceStore:
    def __init__(self, csv_path):
        ...
        self._lock = threading.Lock()

    def _rewrite(self) -> None:
        """Atomic write: temp file + os.replace()."""
        fd, tmp_path = tempfile.mkstemp(
            dir=self._csv_path.parent, prefix=".balance_", suffix=".csv.tmp",
        )
        try:
            with os.fdopen(fd, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self._CSV_HEADERS)
                for bal in self._balances.values():
                    writer.writerow((bal.username, bal.amount, bal.last_claim_at))
            os.replace(tmp_path, self._csv_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise

    def debit(self, username: str, amount: int) -> Balance:
        with self._lock:  # Thread-safe debit
            current = self.get(username)
            if amount < 0:
                raise ValueError("Debit amount must be non-negative")
            if current.amount < amount:
                raise ValueError(...)
            updated = Balance(username=username, amount=current.amount - amount, ...)
            self._balances[username] = updated
            self._rewrite()
            return updated

    def credit(self, username: str, amount: int) -> Balance:
        with self._lock:  # Thread-safe credit
            ...
```

**Blast radius:** Requires `threading.Lock` (already available in stdlib). Temp files created in `data/` directory.

---

## Finding 4: Pydantic Model Validation Gaps

**Severity:** MEDIUM (downgraded from HIGH)
**Verdict:** PARTIALLY CONFIRMED

### Description

`CreateGameRequest` accepts negative integers and arbitrary strings. The impact is overstated: negative `buy_in` causes settlement to be skipped (not wrong payouts), and garbage `token` strings fail later at `Web3.to_checksum_address()`.

### Evidence

`packages/server/src/poker/models.py`:

```python
class CreateGameRequest(BaseModel):
    max_players: int = 0    # accepts -1 (becomes unlimited players)
    token: str | None = None  # accepts "garbage" (fails later at escrow config)
    buy_in: int = 0          # accepts -1 (skips settlement, never settles)
    mode: str | None = None   # accepts "yolo" (undefined behavior in mode checks)
```

Real risk: confusing game state and mode-gating logic, not wrong payouts.

### Proposed Fix

**File:** `packages/server/src/poker/models.py`

```python
from typing import Literal
from pydantic import Field, field_validator
import re

class CreateGameRequest(BaseModel):
    max_players: int = Field(default=0, ge=0, le=10)
    token: str | None = None
    buy_in: int = Field(default=0, ge=0)
    mode: Literal["onchain", "offchain"] | None = None

    @field_validator("token")
    @classmethod
    def validate_token_address(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.match(r"^0x[a-fA-F0-9]{40}$", v):
            raise ValueError("Token must be a valid hex address (0x + 40 hex chars)")
        return v
```

**Blast radius:** Invalid game creation requests now rejected at API boundary with 422.

---

## Finding 5: 100% Rake is Valid (Solidity)

**Severity:** HIGH
**Verdict:** CONFIRMED

### Description

`Escrow.sol::initialize()` checks `if (cfg.rakeBps > MAX_BPS)` — allows `rakeBps == 10000` (100% rake). All payouts become zero, all funds go to rake beneficiary.

### Evidence

`packages/contracts/src/Escrow.sol`:

```solidity
uint16 private constant MAX_BPS = 10_000;
// ...
if (cfg.rakeBps > MAX_BPS) revert InvalidConfig();  // allows == 10000
```

In `_distribute()`: `rake = (gross * 10000) / 10000 = gross`, `net = 0`. All tokens go to `rakeBeneficiary`.

### Proposed Fix

**File:** `packages/contracts/src/Escrow.sol`

```solidity
// BEFORE:
if (cfg.rakeBps > MAX_BPS) revert InvalidConfig();

// AFTER:
if (cfg.rakeBps >= MAX_BPS) revert InvalidConfig();
```

**Blast radius:** None on deployed contracts. New constraint for future deployments.

---

## Finding 6: Empty Payouts Array Accepted (Solidity)

**Severity:** LOW (downgraded from MEDIUM)
**Verdict:** PARTIALLY CONFIRMED

### Description

`settle()` accepts `payouts = []`. **However**, the `payoutSum != balance` check prevents settlement when any deposits exist. The only scenario where empty payouts succeeds is when `balance == 0` (no deposits yet), which is a harmless no-op that wastes an escrow address.

### Evidence

```solidity
if (payoutSum != balance) revert PayoutSumMismatch(balance, payoutSum);
```

With empty payouts: `payoutSum == 0`, so this only passes if `balance == 0`. Funds are NOT bricked.

### Proposed Fix

**File:** `packages/contracts/src/Escrow.sol`

```solidity
// Add at start of settle():
if (payouts.length == 0) revert InvalidConfig();
```

**Blast radius:** Prevents settling with empty payouts. No impact on legitimate settlements.

---

## Finding 7: `address(0)` Accepted as Participant (Solidity)

**Severity:** MEDIUM
**Verdict:** CONFIRMED

### Description

Participant loop validates sort order but not zero address. `[address(0), alice, bob]` is accepted. During expiry, nobody controls `address(0)`, so `withdraw()` can never be called for that slot — funds locked forever.

### Proposed Fix

**File:** `packages/contracts/src/Escrow.sol`

```solidity
for (uint256 i; i < len; ++i) {
    if (cfg.participants[i] == address(0)) revert InvalidConfig();  // ADD THIS
    if (i > 0 && uint160(cfg.participants[i]) <= uint160(cfg.participants[i - 1])) {
        revert ParticipantsNotSorted();
    }
    _participants.add(cfg.participants[i]);
}
```

**Blast radius:** None. Rejects invalid configs only.

---

## Finding 8: Wallet Address Not Validated

**Severity:** MEDIUM
**Verdict:** CONFIRMED

### Description

`game.py::register()` checks for *presence* but not *format* of wallet address. `wallet_address = "hello"` is accepted. Fails later at `Web3.to_checksum_address()` when escrow config is built — delayed, confusing error.

### Proposed Fix

**File:** `packages/server/src/poker/game.py`

```python
import re

def _is_valid_ethereum_address(addr: str) -> bool:
    return bool(re.match(r"^0x[a-fA-F0-9]{40}$", addr))

# In register():
if wallet_address and not _is_valid_ethereum_address(wallet_address):
    raise ValueError("Invalid Ethereum address format")
```

**Blast radius:** On-chain game joins now validate wallet format at registration time.

---

## Finding 9: Division by Zero in `compute_payouts()`

**Severity:** LOW (downgraded from MEDIUM)
**Verdict:** PARTIALLY CONFIRMED

### Description

`compute_payouts()` divides by `starting_chips` with no guard. **However**, the only callers always pass `STARTING_CHIPS = 1000` (a module-level constant). Currently unreachable in practice — defensive coding concern only.

### Proposed Fix

**File:** `packages/server/src/poker/escrow.py`

```python
def compute_payouts(player_chips, buy_in, starting_chips):
    if starting_chips <= 0:
        raise ValueError("starting_chips must be positive")
    if buy_in < 0:
        raise ValueError("buy_in must be non-negative")
    if not player_chips:
        raise ValueError("player_chips cannot be empty")
    ...
```

**Blast radius:** None. Adds preconditions to a pure function.

---

## Finding 10: No Rate Limiting

**Severity:** HIGH
**Verdict:** CONFIRMED

### Description

Zero rate limiting at any layer. No `slowapi`, no middleware, no reverse proxy config. Account spam, game creation spam, and faucet abuse (create unlimited accounts, claim 10k tokens each) are all possible.

### Proposed Fix

**Files:** `packages/server/pyproject.toml`, `packages/server/src/poker/server.py`

```toml
# pyproject.toml — add dependency:
"slowapi>=0.1.9",
```

```python
# server.py — add after app creation:
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to critical endpoints:
@app.post("/api/register", ...)
@limiter.limit("5/minute")
def register_account(req: AccountRegisterRequest, request: Request): ...

@app.post("/api/games", ...)
@limiter.limit("10/minute")
def create_game(req: CreateGameRequest, request: Request): ...
```

**Blast radius:** New dependency. Endpoints return 429 when limit exceeded. Tests may need rate limit disabled via fixture.
