# Changelog: super-merge branch

Merge of upstream/main (Bauti's attestation, fairness, enclave, skills) into dev (Nico's unified routing, nu-front, snapshot buffer).

**Branch:** `super-merge` (based on `dev`)
**Date:** 2026-02-10
**Round 1:** 13 commits, 60 files changed, +4,561 / -538 lines (487 tests)
**Round 2:** 7 steps porting 3 upstream commits (UUID IDs, required mode, escrow guide, feedback)
**Tests:** 503 passed (up from 435 on dev)

---

## Commits (chronological order)

### 1. `17599b9` feat(server): add provable fairness (HMAC-DRBG) and attestation modules
- **New:** `core/fairness.py` — HMAC-DRBG (NIST SP 800-90A) deterministic RNG with commit-reveal
- **New:** `core/attestation.py` — AWS Nitro Secure Module (NSM) attestation via ioctl, COSE_Sign1 CBOR parsing
- Self-contained modules with no routing dependencies

### 2. `c7c054c` feat(db): add seed_hex and seed_commitment columns for provable fairness
- Added `seed_hex` and `seed_commitment` columns to `hand_summaries` and `round_summaries` tables in `db/init.sql`

### 3. `4d28841` feat(server): add attestation and fairness fields to response models
- Added `pcr0_hash`, `admin_signature`, `pcr0` fields to escrow/settlement response models
- Added `seed_commitment`, `seed_hex` fields to game state models
- Added new `AttestationResponse` dataclass

### 4. `f69e4b7` feat(poker): integrate HMAC-DRBG commit-reveal fairness
- `poker/deck.py` — accepts `seed_hex`, uses `FairRng` for deterministic shuffle when provided
- `poker/game.py` — generates seed before each hand, stores seed commitment
- `poker/hand.py` — passes seed to deck, includes seed in hand summary

### 5. `4050d83` feat(dice): integrate HMAC-DRBG commit-reveal fairness
- `dice/game.py` — generates seed per round, uses `FairRng.randbelow(6)` for dice rolls
- Seed commitment published before roll, seed revealed after

### 6. `0a04610` feat(server): add attestation endpoint and seed_commitment in responses
- **New endpoint:** `GET /api/attestation` on Game API
- Added `seed_commitment` to poker/dice state and spectator responses
- Returns NSM attestation document with nonce, PCR values, and server Ethereum address

### 7. `7e2142f` feat(data-api): strip seed_hex from event history, persist seeds in summaries
- Data API strips `seed_hex` from event history responses (prevents early revelation)
- Poker/dice recorders persist `seed_hex` and `seed_commitment` in hand/round summaries

### 8. `b9dd9fd` feat(contracts): add PCR-0 escrow binding and admin signature verification
- `Escrow.sol` — `pcr0Hash` field in config, settlement requires matching PCR-0
- `EscrowFactory.sol` — `createAndDeposit` verifies admin EIP-712 signature, preventing unauthorized escrow creation
- **New:** `EscrowPcr0.t.sol` — PCR-0 binding tests
- Updated all contract test suites

### 9. `08905f9` feat(server): update escrow service for admin signatures and PCR-0
- `escrow_service.py` — fetches PCR-0 from NSM (falls back to zero in dev), generates admin signatures
- `escrow.py` — `sign_create_escrow()` EIP-712 function, `pcr0Hash` in config ABI
- `game_config.py` — added `pcr0_hash` and `admin_signature` fields
- `unified_router.py` / `poker/router.py` — pass through `pcr0_hash`, `admin_signature`, `pcr0` in responses

### 10. `7a16ce5` feat(infra): add Nitro Enclave support (Docker, Terraform KMS, CI)
- **New:** `Dockerfile.game.enclave` — multi-stage build for Nitro Enclave EIF
- **New:** `enclave/init.sh` — vsock proxy + enclave startup
- **New:** `enclave/launch-enclave.sh` — allocator config, EIF launch
- **New:** `kms.tf` — KMS key with Nitro Enclave attestation-based policy
- **New:** `game_api_userdata_enclave.sh.tpl` — enclave-mode EC2 bootstrap
- Updated `ec2_game.tf` with conditional enclave/docker user_data
- Updated `iam.tf` with KMS decrypt permissions
- Updated `build-eif.yml` and `deploy.yml` CI workflows
- ALB rules kept at Nico's `/api/*` convention (did NOT adopt upstream's `/game/*`)

### 11. `778513a` refactor(skills): split into per-game skills with /api/ path convention
- **New:** `.claude/skills/monteclaude/play-poker.md`
- **New:** `.claude/skills/monteclaude/play-dice.md`
- **Deleted:** `.claude/skills/play-monteclaude.md` (replaced by per-game files)
- All paths use `/api/games/` convention, `game_type` in request body

### 12. `a573c11` test: add attestation, fairness, escrow service, and game test suites
- **New:** `test_attestation.py` (322 lines) — attestation endpoint, COSE parsing, dev mode
- **New:** `test_fairness.py` (133 lines) — HMAC-DRBG determinism, seed generation
- **New:** `test_escrow_service.py` (185 lines) — escrow info, settlement with PCR-0
- **New:** `test_game.py` (104 lines) — game lifecycle tests
- Added `TestSignCreateEscrow` to existing `test_escrow.py`

### 13. `f1f12b5` docs: add attestation, fairness verification, and enclave documentation
- **New:** `docs/codebase-audit-2026-02-09.md` — full codebase security audit
- **New:** `docs/two-api-architecture.md` — architecture documentation
- **New:** `examples/verify_attestation.py` — standalone attestation verification script
- Updated `instructions.md` with attestation section, `admin_signature` in escrow docs
- Updated `CLAUDE.md` with attestation/fairness module descriptions
- Added `cbor2>=5.6.0` to `pyproject.toml`

---

## Round 2: Upstream Merge (commits 297c13c, 68c9216, 88b1d25)

### 14. UUID game IDs (int → str)
- `game_id` migrated from sequential `SERIAL` int to `uuid4().hex` string across ~47 files
- DB schema: all `game_id` columns changed from `INTEGER` to `TEXT`
- `GameManager.create_game()` uses `uuid.uuid4().hex` instead of `self._next_id += 1`
- `cleanup_completed()` uses insertion order instead of sort (UUIDs aren't sequential)
- All routers, services, stores, models, recorders, bot, and tests updated atomically

### 15. Required mode in CreateGameRequest
- `mode` field changed from `Literal["onchain", "offchain"] | None` to `Literal["onchain", "offchain"]` (required)
- `infer_mode()` renamed to `validate_mode()` — no longer infers, just validates
- All test game creation calls updated with explicit `"mode": "offchain"` or `"mode": "onchain"`

### 16. Approve calldata builder + escrow guide models
- **New:** `build_approve_calldata(spender, amount)` in `core/escrow.py` — ERC20 approve calldata
- **New models:** `EscrowTxStep`, `EscrowDepositGuide`, `EscrowGuide` in `core/models.py`
- `EscrowInfoResponse` extended with `calldata_approve_factory`, `calldata_approve_escrow`, `guide`

### 17. Escrow guide generation + check_funding error handling
- `escrow_service.get_escrow_info()` now computes approve calldata and builds step-by-step deposit guide
- `escrow_service.check_funding()` wraps `check_deposit_status()` in try/except for undeployed escrow contracts
- Guide uses `/api/games/{id}/funding` (our convention) for verification endpoint

### 18. Token discovery in /api/config
- `GET /api/config` now returns `monte_token_address` and `base_rpc_urls` (4 public Base RPC endpoints)
- Reads `MONTE_TOKEN_ADDRESS` from env

### 19. Feedback endpoints
- **New tables:** `bug_reports`, `questions` (append-only, 10-2000 char body CHECK)
- **New:** `core/feedback_store.py` — `FeedbackStore` with `submit_bug()` and `submit_question()`
- **New endpoints:** `POST /api/accounts/bug` (5/hr), `POST /api/accounts/question` (10/hr)
- Uses `/api/accounts/` prefix (our convention, not upstream's `/api/`)
- **New:** `tests/test_feedback.py` — 14 tests covering auth, validation, rate limits, isolation, persistence

### 20. Documentation updates
- `instructions.md` — added feedback section, updated API reference table
- `play-poker.md`, `play-dice.md` — added bug reports section and table entries
- `CHANGELOG-super-merge.md` — this section

**Tests after round 2:** 503 passed (up from 487)

---

## What Was Preserved from dev (NOT merged from upstream)

- **Unified routing** (`/api/games/*`) — did not adopt upstream's `/game/{type}/*` convention
- **nu-front** (Next.js frontend) — kept intact
- **snapshot_buffer.py** — kept intact
- **unified_router.py** — kept intact, extended with new fields
- **ALB routing rules** — kept `/api/*` path patterns

## Known Issues / Follow-ups

- **Missing ALB rule for attestation:** `GET /api/attestation` is served by the Game API but has no dedicated ALB listener rule. In production, this would fall through to the Data API (default) and return 404. Needs a new listener rule at ~priority 450 routing `GET /api/attestation` to the Game API target group.
- **Contract E2E tests:** 5 E2E tests in `packages/contracts/test/E2E.t.sol` require a mainnet fork RPC and are expected to fail without one.
- **Enclave testing:** Enclave-specific code paths (NSM ioctl, KMS decrypt) can only be tested inside a real Nitro Enclave. Dev mode gracefully falls back.
