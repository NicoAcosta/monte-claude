# Escrow Design: On-Chain Token Escrow for Claude Poker

## Overview

Claude Poker runs entirely off-chain with virtual chips. This escrow system lets players deposit real ERC-20 tokens (on Base chain) as buy-in, play poker off-chain, and settle winnings on-chain via an admin-signed settlement.

The on-chain module is a **generic time-based escrow protocol** — it knows nothing about poker and can be reused for any multi-party game or competition.

The off-chain server never submits transactions. It generates escrow parameters, monitors deposits via RPC, and signs EIP-712 settlements.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Settlement distribution | Push with try/catch, failed transfers stored for pull-based claim | Handles fee-on-transfer and reverting tokens gracefully |
| Server transactions | None. Server only generates data for players to transact | Keeps server stateless w.r.t. chain, no gas management needed |
| Token support | All tokens allowed (isolated proxy per escrow). MVP: bluechip only (USDC, WETH, WBTC, USDT) | Proxy isolation prevents cross-escrow token interference |
| Game ID entropy | Server-provided randomness (trusted via TEE) | Simple, no on-chain randomness needed |
| First deposit | Factory batches deploy + first deposit atomically | Single transaction UX for first depositor |
| Admin identity | Server EOA per escrow, set at init | Simple key management, one signer per game |
| Rake | Percentage (basis points), configured per escrow | Flexible per-game rake configuration |
| Rake mechanics | Payouts sum to escrow balance; escrow deducts rake proportionally | Clean separation: server computes gross payouts, contract handles rake |
| Permit2 | Deferred to follow-up | MVP uses standard approve + deposit |
| Player wallet | Provided per-game when joining (not stored on account) | Players can use different wallets per game |
| Buy-in | Fixed per game, equal for all participants | Simplest model, no variable stacks |
| Chip mapping | Internal chips unchanged (1000 start, 10/20 blinds). Settlement maps proportionally | `payout_i = chips_i * buy_in / STARTING_CHIPS` |

## State Machine

```
FUNDING ──[all deposited]──→ ACTIVE ──[valid settlement]──→ SETTLED
    │                            │
    │ [funding deadline,         │ [settlement deadline]
    │  not all deposited]        │
    ↓                            ↓
    └────────────────────────→ EXPIRED ──→ withdraw (no rake, depositors only)
```

- **FUNDING**: Waiting for all participants to deposit. Auto-transitions to ACTIVE when last deposit lands.
- **ACTIVE**: All deposits received, game in progress. Settlement can happen anytime.
- **SETTLED**: Admin submitted valid settlement signature, payouts distributed (minus rake).
- **EXPIRED**: Deadline passed without full deposits or settlement. Depositors can withdraw original amounts (no rake).

Settlement is also valid from FUNDING state (early settlement before all deposits).

## Architecture

### On-Chain (Solidity / Foundry)

- **Escrow.sol**: Implementation contract behind minimal proxy. Holds all escrow logic.
- **EscrowFactory.sol**: Deploys minimal proxies (EIP-1167) via CREATE2 for deterministic addresses.

### Off-Chain (Python / FastAPI)

- **escrow.py**: Pure functions for CREATE2 address computation, calldata building, EIP-712 signing, payout calculation.
- **server.py**: New endpoints for escrow info, funding status, settlement.
- **game.py**: Extended with wallet addresses, max players, buy-in, funded flag.

### Flow

1. Game created with `token`, `buy_in`, `max_players`
2. Players join with `wallet_address`
3. When game is full, server generates escrow config
4. First player calls `factory.createAndDeposit()` (deploys proxy + deposits atomically)
5. Remaining players call `escrow.deposit()` directly
6. Server polls chain for deposit status
7. When all deposited, game starts
8. Game plays off-chain (normal poker)
9. When game ends, server signs EIP-712 settlement
10. Anyone submits settlement to escrow contract
11. Contract distributes payouts minus rake
