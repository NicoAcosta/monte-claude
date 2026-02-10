# Agent Playtest Notes — 2026-02-10

Two Haiku agents attempted to play funded poker on a local Anvil Base fork with MONTE tokens.

## Setup
- Anvil fork of Base (chain 8453) on localhost:8545
- MONTE deployed at `0x392dB05b3e4d4b61338c768318e825a52Bd9Fe43`
- EscrowFactory at `0xD00cBc0dD77f639007cA239401F73618731Fae6C`
- Game API :8001, Data API :8000, Account API :8002
- Each agent given an Anvil private key + wallet address

## Issue 1: Route discovery — `/api/games` vs `/game/poker/games` (HIGH)

Both agents initially tried `POST /api/games` (Data API, read-only) to create a game. This returned 404 or wrong results. They had to **read source code** to discover that the correct endpoint is `POST /game/poker/games` on the Game API.

**Root cause:** The instructions at `/api/play` reference endpoints like `POST $SERVER/poker/games` but with `$SERVER` pointing to `https://monteclaude.ai`. In production, ALB routing makes both `/api/*` and `/game/poker/*` work on the same domain. Locally, they're different ports (8000 vs 8001), so the agents get confused.

**Fix options:**
- Add a "Local development" section to the play skill with explicit port-mapped URLs
- Add a `/api/games` POST passthrough on the Game API that redirects or errors with a helpful message
- Make the lobby endpoint on the Game API serve game creation too (already serves list at `GET /api/games`?)

## Issue 2: Escrow deposit flow too complex for agents (HIGH)

Neither agent successfully completed the `createAndDeposit` call. The flow requires:
1. Get `/escrow` → extract `calldata_create_and_deposit` (a massive hex blob)
2. Approve factory for token spending
3. `cast send $FACTORY $CALLDATA --rpc-url ... --private-key ...`

**Problems encountered:**
- Agents didn't understand the difference between first depositor (`createAndDeposit` on factory) vs subsequent depositor (`deposit` on escrow)
- Agent 1 approved the escrow address instead of the factory, then called deposit on a non-existent escrow
- Agent 2 tried `createAndDeposit` but the raw calldata failed (likely shell escaping of the hex blob)
- The `/funding` endpoint returned 500 (because the escrow contract doesn't exist on-chain yet)

**Fix options:**
- Provide explicit curl+cast command sequences in the `/escrow` response (not just raw calldata)
- Add a "Quick deposit guide" section to the play instructions with step-by-step cast commands
- Consider a server-side deposit helper that wraps the on-chain call
- Better error message from `/funding` when escrow isn't deployed yet (currently 500)

## Issue 3: JSON escaping in curl (MEDIUM)

Both agents struggled with JSON payloads in curl, especially when values contain quotes or special characters. They tried various workarounds (temp files, heredocs, different quoting strategies).

**Fix options:**
- Show both `curl -d '{"key": "value"}'` AND file-based approaches in examples
- This may be a Haiku-specific limitation — smarter models handle shell escaping better

## Issue 4: WebFetch failed for localhost (LOW)

Both agents' initial `WebFetch` calls to `http://localhost:8000/api/play` failed, forcing them to fall back to `curl` via Bash. This is expected (WebFetch doesn't reach localhost) but added friction.

**Not actionable** — this is a tool limitation, not a docs issue.

## Issue 5: Game listing route confusion (MEDIUM)

The lobby endpoint `GET /api/games` is on the Data API (:8000), but game creation `POST /poker/games` is on the Game API (:8001). Agent 2 successfully listed games on :8000 but tried to create on :8000 too.

**Fix options:**
- Mirror game creation on the Data API with a redirect/error pointing to Game API
- Or: add game creation to the Game API's `/api/games` endpoint (it already has GET)

## Issue 6: Agent 2 created its own game instead of joining Agent 1's (LOW)

Agent 2 was supposed to wait and join Agent 1's game, but after not finding it immediately, created its own funded game. Both agents ended up in separate games before eventually finding each other.

**Fix options:**
- The lobby query works fine — this is more about agent coordination timing
- Could add a "find open games" helper endpoint that filters by game_type + has_open_seats

## Outcome

Agents successfully: registered, claimed MONTE faucet, discovered correct routes (after reading source), created/joined games, retrieved escrow config.

Agents failed at: completing the on-chain escrow deposit. The funded game never started. Agent 2 pivoted to creating free offchain games as a fallback.

## Issue 7: False positive on deposit — agents can't verify escrow deployment (MEDIUM)

Agent 2 claimed it "successfully deposited" to the escrow address, but `cast code` on that address returned `0x` (no contract). What actually happened: the agent approved the factory, then called `deposit()` on the predicted escrow address (which has no code). The tx "succeeded" (status 1) because sending to an EOA with calldata is valid EVM — it just does nothing. The agent had no way to know the deposit didn't work.

**Fix options:**
- After deposit, the agent should verify with `/funding` endpoint — but that was returning 500 (Issue 2)
- The `/escrow` response could include a "verification" section: "After depositing, call `GET /funding` and confirm your address shows `deposited: true`"
- Consider a `cast code $ESCROW_ADDRESS` check step in the instructions

## Priority Fixes

1. **Explicit local dev URLs** in play instructions (port-mapped)
2. **Step-by-step cast commands** in `/escrow` response or play instructions for the deposit flow
3. **Better /funding error** when escrow contract not yet deployed (not 500)
4. **Route clarity** — consider unifying game creation under a single consistent path
