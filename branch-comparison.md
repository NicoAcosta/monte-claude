# Branch Comparison: upstream/main (Bauti) vs dev (Nico)

Side-by-side comparison of all changes since local `main`, organized by area.

- **Bauti** (`upstream/main`): 4 commits, 136 files, +5,455 / -7,193
- **Nico** (`dev`): 26+ commits, 61 files, +4,955 / -844

---

## Quick Reference

| Area | Bauti | Nico | Recommendation |
|------|-------|------|----------------|
| Frontend (nu-front) | Deleted | Major improvements | **Keep Nico's** |
| Database | seed columns added | No changes | **Take Bauti's** |
| Game API routing | `/game/{type}/` | `/api/games/` unified | **Nico's routing** |
| Attestation | New endpoint + module | — | **Take Bauti's** |
| Fairness (RNG) | HMAC-DRBG commit-reveal | — | **Take Bauti's** |
| Data API | seed_hex stripping | `/api/` prefix | **Both** |
| Account API | No changes | `/api/accounts/` | **Keep Nico's** |
| Contracts | PCR-0 + admin sigs | No changes | **Take Bauti's** |
| Infra (enclave) | Full Nitro Enclave | — | **Take Bauti's** |
| Infra (ALB) | `/game/*` wildcard | `/api/*` priority rules | **Nico's ALB** |
| Skills | Per-game split | Path updates | **Bauti's structure + Nico's paths** |
| Game logic (poker/dice) | Fairness integration | No changes | **Take Bauti's** |
| Bot client | No changes | `/api/` paths | **Keep Nico's** |
| Tests | 6 new test files | Path updates | **Merge both** |
| Docs | Attestation/enclave | Path convention | **Merge both** |

---

## Detailed Comparison

### 1. Frontend (`packages/nu-front/`)

| | Bauti | Nico |
|---|---|---|
| **Action** | Deleted entirely (95 files, ~5,885 lines) | 41 files changed (+3,861 -317) |
| **Routing** | — | Next.js rewrites updated to `/api/games/*`, `/api/streams/*` |
| **Data layer** | — | Migrated to `"use cache"` + `cacheLife()` + `cacheTag()` (Next.js 16 PPR) |
| **Config** | — | `cacheComponents: true` in next.config.ts |
| **Hooks** | — | Fixed: abort controller in usePoll, state-based fallback in useGameStream, setTimeout leak in useReplayQueue, render-time side effects in narration/audio |
| **Components** | — | Shared icons extracted, React.memo on GameCard/PlayerSeat, FundingDot extracted from IIFE |
| **Design** | — | 11 spectator color tokens added to globals.css, ~40 hardcoded hex values replaced |
| **UX** | — | Loading skeletons (5 routes), error boundaries (3 levels), mobile hamburger nav, skip-to-content, noscript fallbacks, custom 404 |
| **Images** | — | Hero: 16 `next/image` replaced with plain `<img>`. Nav: `sizes="36px"` on logo |
| **Hydration** | — | CopyrightYear client component + Suspense, TimeAgo client component |
| **Replacement** | Static HTML in `packages/frontend/` | — |

**Who's ahead:** Nico

**Recommendation:** **Keep Nico's nu-front.** The static HTML in `packages/frontend/` can coexist as a lightweight spectator page, but nu-front is the production frontend with PPR, caching, error handling, a11y, and mobile support.

---

### 2. Database

| | Bauti | Nico |
|---|---|---|
| **Schema** | Added `seed_hex` + `seed_commitment` columns to `hand_summaries` and `round_summaries` | No changes |

**Who's ahead:** Bauti

**Recommendation:** **Take Bauti's.** Additive columns with defaults — no conflict risk.

---

### 3. Game API (`packages/server/src/game_api/`)

#### Routing Architecture

| | Bauti | Nico |
|---|---|---|
| **Pattern** | `/game/poker/*`, `/game/dice/*` | `/api/games/*` (unified) |
| **Routers** | Two separate: `poker_router` at `/game/poker`, `dice_router` at `/game/dice` | One `unified_router` at `/api/games` (591 lines) |
| **Game type** | In URL path prefix | In request body (`game_type` param on create) |
| **Adding a game** | New router + new ALB rule | Register new game_type value (no infra changes) |

**Why Nico's is better:** REST best practices — games are a single resource type, game_type is an attribute. Cleaner namespace (`/api/accounts/`, `/api/games/`, `/api/streams/`). One ALB wildcard. Client simplicity — URLs don't encode game type.

#### New Modules (Bauti-only)

| Module | Lines | Purpose |
|--------|-------|---------|
| `core/attestation.py` | 222 | NSM ioctl, COSE_Sign1 parsing, dev-mode fallback |
| `core/fairness.py` | 93 | HMAC-DRBG RNG, SeedCommitment, FairRng, Fisher-Yates shuffle |

#### Endpoint Differences

| Endpoint | Bauti | Nico |
|----------|-------|------|
| Create game | `POST /game/poker/games` | `POST /api/games` |
| Join | `POST /game/poker/{id}/join` | `POST /api/games/{id}/join` |
| State | `GET /game/poker/{id}/state` | `GET /api/games/{id}/state` |
| Action | `POST /game/poker/{id}/action` | `POST /api/games/{id}/action` |
| Spectator | `GET /game/poker/{id}/spectator` | `GET /api/games/{id}/spectator` |
| Attestation | `GET /attestation` | — |
| Snapshots | Removed | `GET /api/games/{id}/spectator/snapshots` |

#### Other Differences

| | Bauti | Nico |
|---|---|---|
| `SERVER_PRIVATE_KEY` | Required at startup | Not present |
| Snapshot buffer | Deleted entirely | Integrated into unified router |
| Seed commitment | In spectator + player state responses | Not present |

**Who's ahead:** Both — conflicting routing + unique features on each side

**Recommendation:** **Nico's unified router + port Bauti's attestation + fairness.** Specifically:
- Keep `unified_router.py` and `/api/games/` convention
- Add `core/attestation.py` and `core/fairness.py` as-is
- Add `GET /api/attestation` endpoint to game_api/app.py
- Add `SERVER_PRIVATE_KEY` env var
- Update unified router to include seed_commitment in responses

---

### 4. Data API (`packages/data_api/`)

| | Bauti | Nico |
|---|---|---|
| **Paths** | No path changes | `/game/{id}/streams` → `/api/games/{id}/streams` |
| **Logic** | Strips `seed_hex` from event history API | No logic changes |

**Who's ahead:** Both contribute

**Recommendation:** **Keep Nico's paths + add Bauti's seed_hex stripping logic.**

---

### 5. Account API (`packages/account_api/`)

| | Bauti | Nico |
|---|---|---|
| **Paths** | Unchanged (`/api/register`, `/api/faucet`, `/api/balance`) | `/api/accounts/register`, `/api/accounts/faucet`, `/api/accounts/balance` |

**Who's ahead:** Nico

**Recommendation:** **Keep Nico's.** Clean namespace separation: `/api/accounts/*` vs `/api/games/*`.

---

### 6. Smart Contracts (`packages/contracts/`)

| | Bauti | Nico |
|---|---|---|
| **Escrow.sol** | `pcr0Hash` field, `settle()` takes `bytes pcr0`, verifies hash | No changes |
| **EscrowFactory.sol** | Admin signature verification (EIP-712) on `createEscrow()` | No changes |
| **Tests** | `EscrowPcr0.t.sol` (192 lines), updated `Escrow.t.sol`, `EscrowFactory.t.sol`, `E2E.t.sol`, `BaseEscrowTest.sol` | No changes |

**Who's ahead:** Bauti — entirely new work

**Recommendation:** **Take all of Bauti's contract changes.** Zero conflicts with Nico's branch.

---

### 7. Infrastructure

#### Enclave (Bauti-only)

| File | Lines | Purpose |
|------|-------|---------|
| `infra/docker/Dockerfile.game.enclave` | 74 | Multi-stage: kmstool build + Python runtime |
| `infra/docker/enclave/init.sh` | 111 | Vsock bridges, DB tunnel, KMS decrypt, API start |
| `infra/docker/enclave/launch-enclave.sh` | 119 | EIF build, nitro-cli launch, shutdown |
| `infra/terraform/kms.tf` | 68 | KMS key with PCR-0 attestation policy |
| `infra/terraform/secrets.tf` | 13 | Secrets Manager |
| `infra/terraform/templates/game_api_userdata_enclave.sh.tpl` | 187 | EC2 userdata for enclave instances |
| `infra/terraform/variables.tf` | +14 | `enclave_enabled`, `enclave_pcr0` |
| `.github/workflows/build-eif.yml` | 119 | Builds EIF, extracts PCRs, optional release |
| `.github/workflows/deploy.yml` | +41 | Conditional enclave deployment |

#### ALB Routing

| | Bauti | Nico |
|---|---|---|
| **Approach** | Single `/game/*` wildcard (priority 200) | 8 priority-based rules for `/api/accounts/*`, `/api/games/*`, `/api/streams/*` |
| **Adding a game** | No change needed (wildcard) | No change needed (wildcard under `/api/games/*`) |

**Who's ahead:** Both — Bauti has enclave infra, Nico has cleaner ALB rules

**Recommendation:** **Take Bauti's enclave infra (Docker, Terraform, CI) + use Nico's ALB rules** updated to include enclave toggles. The ALB rules need to match `/api/*` paths, not `/game/*`.

---

### 8. Skills (`.claude/skills/`)

| | Bauti | Nico |
|---|---|---|
| **Structure** | Deleted `play-monteclaude.md`. Created `monteclaude/play-poker.md` (268 lines) + `monteclaude/play-dice.md` (224 lines) | Updated `play-monteclaude.md` paths to `/api/*` |
| **Content** | Attestation verification examples, fairness seed checking, per-game endpoints | Correct `/api/` paths |
| **Paths** | `/game/poker/games`, `/game/dice/games` | `/api/games` |

**Who's ahead:** Bauti (structure) + Nico (paths)

**Recommendation:** **Take Bauti's per-game structure + update all paths to `/api/` convention.** Add attestation + fairness docs. Delete the monolithic `play-monteclaude.md`.

---

### 9. Game Logic (`packages/server/src/poker/`, `src/dice/`)

| | Bauti | Nico |
|---|---|---|
| **poker/hand.py** | Seed commitment integration, `FairRng` deck shuffle | No changes |
| **poker/deck.py** | `shuffle_deck(deck, rng: FairRng)` replaces `random.shuffle()` | No changes |
| **poker/game.py** | `generate_seed()` per hand, seed revealed in summary | No changes |
| **poker/router.py** | Simplified spectator response, removed snapshot buffer | No changes (unified router handles routing) |
| **dice/game.py** | Seed commitment + `FairRng` for dice rolls | No changes |
| **dice/router.py** | Route prefix changes | No changes |

**Who's ahead:** Bauti — fairness is deep in game logic

**Recommendation:** **Take Bauti's game logic changes.** Fairness (seed commitment, FairRng shuffle, deterministic dice) is orthogonal to routing. These changes apply cleanly.

---

### 10. Bot Client (`packages/bot/`)

| | Bauti | Nico |
|---|---|---|
| **client.py** | No changes | New constructor: `Client(server, game_server=None, account_server=None)`. All paths updated to `/api/accounts/*` and `/api/games/*`. Added `game_type` param to `create_game()` |
| **\_\_main\_\_.py** | No changes | Simplified arg names |

**Who's ahead:** Nico

**Recommendation:** **Keep Nico's.** Bot is a consumer — it should match the API convention.

---

### 11. Tests

| | Bauti | Nico |
|---|---|---|
| **Existing tests** | Paths updated to `/game/{type}/` | Paths updated to `/api/games/` |
| **test_attestation.py** | NEW (322 lines) | — |
| **test_escrow_service.py** | NEW (185 lines) | — |
| **test_fairness.py** | NEW (133 lines) | — |
| **test_game.py** | NEW (104 lines) | — |
| **test_dice_game.py** | NEW (96 lines) | — |
| **test_hand.py** | NEW (62 lines) | — |
| **EscrowPcr0.t.sol** | NEW (192 lines) | — |

**Who's ahead:** Both — conflicting path conventions + Bauti has 7 new test files

**Recommendation:** **Keep Nico's path convention in existing tests + take Bauti's new test files** (updating their paths from `/game/{type}/` to `/api/games/`).

---

### 12. Documentation

| File | Bauti | Nico |
|------|-------|------|
| `README.md` | Rewritten: removed nu-front docs, single entry point | No changes |
| `instructions.md` | Added attestation + fairness verification, `/game/{type}/` paths | Version 2.0, `/api/` paths |
| `CLAUDE.md` | Attestation section added | Minor path updates |
| `infra/ARCHITECTURE.md` | Complete rewrite for enclave architecture | Updated routing tables for `/api/` |
| `docs/codebase-audit-2026-02-09.md` | NEW | — |
| `docs/two-api-architecture.md` | NEW | — |
| `examples/verify_attestation.py` | NEW (316 lines) | — |
| `dev-changelog.md` | — | NEW |

**Recommendation:** **Merge both.** Take Bauti's attestation/fairness/enclave documentation + new doc files. Use Nico's path convention throughout. Keep README references to nu-front (don't merge Bauti's removal of frontend docs).

---

## Merge Strategy

### Phase 1: Take Bauti's non-conflicting additions
These can be cherry-picked or manually applied with no conflicts:
- `core/attestation.py` (new file)
- `core/fairness.py` (new file)
- `packages/contracts/` changes (all new/modified)
- `infra/docker/Dockerfile.game.enclave` (new file)
- `infra/docker/enclave/` scripts (new files)
- `infra/terraform/kms.tf`, `secrets.tf` (new files)
- DB schema additions (`seed_hex`, `seed_commitment` columns)
- New test files (attestation, fairness, escrow, game, dice, hand)
- New doc files (codebase audit, two-api architecture, verify_attestation.py)

### Phase 2: Port Bauti's game logic into Nico's structure
These require manual integration:
- `poker/hand.py`: add seed commitment fields + FairRng shuffle
- `poker/deck.py`: replace `random.shuffle` with `FairRng`
- `poker/game.py`: add `generate_seed()` per hand
- `dice/game.py`: add seed commitment + FairRng dice rolls
- `game_api/app.py`: add `/api/attestation` endpoint + `SERVER_PRIVATE_KEY`
- `data_api/app.py`: add seed_hex stripping from event history
- Unified router: include seed_commitment in state/spectator responses

### Phase 3: Adapt Bauti's infra to Nico's paths
- ALB rules: use Nico's `/api/*` patterns + add Bauti's enclave toggles
- CI/CD: update deploy workflow health checks to `/api/` paths
- Skills: take Bauti's per-game split, update all paths to `/api/`
- Docs: merge attestation/fairness sections into instructions v2.0

### Phase 4: Don't merge
- nu-front deletion (keep Nico's frontend)
- Bauti's route convention (`/game/{type}/`) — use Nico's `/api/games/`
- Snapshot buffer deletion — keep Nico's integration
- README removal of frontend docs

---

## Conflict Hotspots

These files were modified on both branches and will need manual resolution:

| File | Conflict Type |
|------|--------------|
| `packages/server/src/game_api/app.py` | Routing architecture (separate routers vs unified) |
| `packages/server/src/poker/router.py` | Snapshot buffer removal vs no changes |
| `packages/server/tests/test_game_api.py` | Path convention (`/game/{type}/` vs `/api/games/`) |
| `packages/server/tests/test_dice_api.py` | Same path conflict |
| `packages/server/tests/test_data_api.py` | Same path conflict |
| `packages/server/tests/test_offchain_games.py` | Same path conflict |
| `infra/terraform/alb.tf` | Routing rules (wildcard vs priority) |
| `infra/ARCHITECTURE.md` | Both rewrote routing tables |
| `instructions.md` | Both updated paths + Bauti added attestation sections |
| `CLAUDE.md` | Both made small updates |
| `.claude/skills/play-monteclaude.md` | Bauti deleted it, Nico updated it |
