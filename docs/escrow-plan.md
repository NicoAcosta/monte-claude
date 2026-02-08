# Implementation Plan: On-Chain Token Escrow

See [escrow-design.md](escrow-design.md) for design decisions and architecture overview.

## On-Chain Contracts

### Escrow.sol

**Config (immutable after init):**
- `token` (address), `admin` (address), `rakeBeneficiary` (address)
- `depositAmount` (uint256), `rakeBps` (uint16)
- `fundingDeadline` (uint256), `settlementDeadline` (uint256)
- `participants` (address[])

**Functions:**
- `initialize(config, factory)` — once, called by factory
- `deposit(participant)` — transferFrom, credit participant, auto-transition FUNDING → ACTIVE
- `recordDeposit(participant)` — factory-only, records deposit when factory transferred tokens
- `settle(payouts[], signature)` — EIP-712 verify, distribute minus rake, push + try/catch
- `expire()` — transitions to EXPIRED if past deadline
- `withdraw()` — EXPIRED only, returns depositAmount to depositors
- `claimFailed()` — SETTLED only, pull-based claim for failed push transfers

### EscrowFactory.sol

- `createAndDeposit(config, salt)` — deploy proxy + first deposit atomically
- `getEscrowAddress(config, salt)` — deterministic CREATE2 address
- `implementation()` — view

### EIP-712 Settlement

```
Domain: { name: "TimeBasedEscrow", version: "1", chainId, verifyingContract }
Settle: { Payout[] payouts }
Payout: { address recipient, uint256 amount }
```

### Test Plan

- Unit: deposit, expire, withdraw, settle, claimFailed, state transitions
- Fuzz: payout distributions, deposit ordering, rake bps, timestamps
- E2E: Base fork with real USDC, full lifecycle + failure paths

## Off-Chain Changes

### New: `src/poker/escrow.py`

Pure functions:
- `compute_escrow_address` — CREATE2 deterministic
- `build_create_and_deposit_calldata` — ABI encode for factory
- `build_deposit_calldata` — ABI encode for escrow.deposit
- `check_all_deposited` — RPC poll
- `check_deposit_status` — per-participant RPC poll
- `sign_settlement` — EIP-712 signing
- `compute_payouts` — chips → token amounts

### Modified: `game.py`

- `RegisteredPlayer`: add `wallet_address: str | None`
- `Game.__init__`: add `max_players`, `token`, `buy_in`
- `Game.register()`: accept wallet_address, reject if full
- `Game.is_full` property
- `Game.funded` flag (set by server when deposits confirmed)
- `Game.start()`: require funded or buy_in == 0

### New endpoints in `server.py`

- `GET /game/{id}/escrow` — config + calldata (only when full)
- `GET /game/{id}/funding` — deposit status via RPC
- `GET /game/{id}/settlement` — EIP-712 signed settlement (game over only)

### Modified endpoints

- `POST /api/games` — accept max_players, token, buy_in
- `POST /game/{id}/join` — accept wallet_address
- `POST /game/{id}/start` — require funded for buy_in > 0

## Implementation Order

1. Docs (this file + design doc)
2. Foundry setup (contracts/, OpenZeppelin)
3. Escrow.sol
4. EscrowFactory.sol
5. Foundry tests (unit + fuzz + E2E)
6. Python escrow module + tests
7. Game lifecycle changes
8. Server endpoints + tests
9. Full test suite verification
