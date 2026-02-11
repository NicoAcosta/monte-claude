# Upstream Changelog (bauti-defi/claude-poker main)

Changes on `upstream/main` since our local `main` — 4 commits, 136 files changed, +5,455 / -7,193.

---

## Commits

| Hash | Title | PR |
|------|-------|----|
| `c7de68c` | refactor(skills): split play-monteclaude into per-game skills | #39 |
| `acf303c` | feat(server): attestation endpoint, admin signature verification, PCR-0 escrow | #40 |
| `d0c9189` | feat(infra): Nitro Enclave support + unified /game/* ALB routing | #37 |
| `baae153` | feat(server): per-round commit-reveal provable fairness | #41 |

---

## 1. Skills Split (`c7de68c`)

Replaced the monolithic `.claude/skills/play-monteclaude.md` (308 lines) with two game-specific skills:

- **`.claude/skills/monteclaude/play-poker.md`** (268 lines) — poker-specific: escrow, funded game flows, offchain settlement
- **`.claude/skills/monteclaude/play-dice.md`** (224 lines) — dice-specific: offchain only, no escrow endpoints

Also fixes: `chat` field renamed to `chat_log`, removed incorrect `requires_auth` from GET endpoints, added missing `/game/{id}/offchain-settlement` docs for poker.

---

## 2. Attestation + Admin Signatures + PCR-0 Escrow (`acf303c`)

### New: `core/attestation.py` (222 lines)

Low-level NSM (Nitro Secure Module) integration for enclave identity proof:

- Raw ioctl to `/dev/nsm` via ctypes (no third-party NSM library)
- COSE_Sign1 CBOR parsing with `cbor2`
- Returns `AttestationResult` with PCR-0/1/2 values, certificate chain, nonce
- **Dev-mode fallback**: when `/dev/nsm` unavailable, returns synthetic attestation with all-zero PCRs (`module_id: "dev-mode"`)
- Pure functions, frozen dataclasses, fully testable

### New: `GET /attestation` endpoint

Added to game API — returns base64-encoded attestation document + parsed PCR values. Embeds server Ethereum address as `user_data` (20 bytes). Accepts optional hex nonce for replay protection.

### Admin Signature Verification

- `core/escrow.py` gains `sign_create_escrow()` — EIP-712 signing of escrow configs
- `EscrowFactory.sol` now verifies admin signature on `createEscrow()` — prevents unauthorized factory deployments

### PCR-0 Escrow Binding

- `Escrow.sol`: new `bytes32 pcr0Hash` field in config struct
- `settle()` signature changed: `settle(Payout[], bytes pcr0, bytes signature)`
- If `pcr0Hash != bytes32(0)`, settlement verifies `keccak256(pcr0) == pcr0Hash`
- Binds game settlement to specific enclave code version

### Env Var Requirement

`SERVER_PRIVATE_KEY` required at startup — used to derive server Ethereum address. Game API crashes without it. Makefile default: Anvil account #0 deterministic key.

### New Tests

- `test_attestation.py` (322 lines) — 15 tests: nonce validation, PCR parsing, cert chain, dev mode fallback
- `test_escrow_service.py` (185 lines) — 8 tests: EIP-712 signing, CREATE_ESCROW verification
- `EscrowPcr0.t.sol` (192 lines) — PCR-0 escrow flows, revert on mismatch

### Documentation

- `instructions.md`: "Server Verification (Attestation)" section with full cryptographic verification workflow
- `examples/verify_attestation.py` (316 lines): standalone verification script (COSE decode, cert chain, ECDSA)
- `CLAUDE.md`: attestation section added

---

## 3. Nitro Enclave Infrastructure (`d0c9189`)

### Enclave Dockerfile (`infra/docker/Dockerfile.game.enclave`)

Multi-stage build:
1. **Stage 1**: compiles `kmstool_enclave_cli` from AWS Nitro SDK (builds aws-lc crypto library)
2. **Stage 2**: amazonlinux:2023 runtime with Python 3.11, socat, kmstool binary, app code

### Enclave Launch Scripts

- **`infra/docker/enclave/init.sh`** (111 lines): vsock bridges, PostgreSQL tunneling, KMS key decryption, Game API startup + monitoring
- **`infra/docker/enclave/launch-enclave.sh`** (119 lines): EIF build, enclave launch via nitro-cli, graceful shutdown

### Terraform

- **`kms.tf`** (68 lines): KMS key with PCR-0 attestation policy — only decrypts if enclave image hash matches
- **`secrets.tf`** (13 lines): Secrets Manager for enclave values
- **`templates/game_api_userdata_enclave.sh.tpl`** (187 lines): EC2 userdata for enclave instances
- **`variables.tf`**: `enclave_enabled` (bool) + `enclave_pcr0` (string) feature flags
- **`ec2_game.tf`**, **`iam.tf`**: conditional enclave IAM roles + instance config

### ALB Routing Simplification

Replaced 8 specific ALB rules with a single wildcard:
```
Priority 200: Any /game/* → Game API
Priority 400: POST /stream/* → Game API
Priority 410: GET /stream/*/data → Game API
Default: Everything else → Data API
```

### Server Route Changes

- `app.include_router(poker_router, prefix="/game/poker")` (was `/poker`)
- `app.include_router(dice_router, prefix="/game/dice")` (was `/dice`)

### Snapshot Buffer Removal

Deleted `core/snapshot_buffer.py` and all related endpoints (`/spectator/snapshots`, `/snapshots`). Spectator state now served directly.

### CI/CD

- **`.github/workflows/build-eif.yml`**: now functional (was placeholder). Builds enclave Docker image, runs `nitro-cli build-enclave`, extracts PCR-0/1/2, can publish as GitHub release
- **`.github/workflows/deploy.yml`**: conditional Dockerfile selection based on `ENCLAVE_ENABLED` secret

### Architecture Docs

`infra/ARCHITECTURE.md` rewritten with Phase 2 enclave architecture:
```
PARENT EC2:
  [socat]       TCP:8001 ←→ VSOCK:CID16:8001  (ALB inbound)
  [vsock-proxy]  VSOCK:5432 → RDS              (DB outbound)
  [vsock-proxy]  VSOCK:443  → RPC/KMS          (HTTPS outbound)

ENCLAVE (CID 16):
  [socat]       VSOCK:8001 ←→ TCP:127.0.0.1:8001
  [kmstool]     Decrypt SERVER_PRIVATE_KEY via KMS attestation
  [uvicorn]     Game API on 127.0.0.1:8001
```

---

## 4. Commit-Reveal Provable Fairness (`baae153`)

### New: `core/fairness.py` (93 lines)

NIST SP 800-90A HMAC-DRBG implementation:

- `generate_seed() → SeedCommitment` — 32 random bytes + SHA-256 commitment
- `verify_seed(seed_hex, commitment) → bool` — timing-safe comparison
- `FairRng` class: HMAC-DRBG generator with `generate()`, `randbelow()`, `shuffle()` (Fisher-Yates)
- **Deterministic & reproducible**: same seed produces identical output in any language implementing NIST spec

### Game Integration

**Poker**: before each hand, `generate_seed()` creates commitment. Deck shuffled with `FairRng(seed)`. After hand completes, `seed_hex` revealed in hand summary. Clients can replay shuffle to verify.

**Dice**: same pattern — `FairRng.randbelow(6)` for each die. Seed revealed in round summary.

### DB Schema

```sql
ALTER TABLE hand_summaries ADD COLUMN seed_hex TEXT, seed_commitment TEXT;
ALTER TABLE round_summaries ADD COLUMN seed_hex TEXT, seed_commitment TEXT;
```

### API Responses

Spectator and player state responses now include `seed_commitment` (before hand) and `seed_hex` (after hand). Data API strips `seed_hex` from event history to prevent early revelation.

### Verification Flow

```
1. Client receives seed_commitment before hand starts
2. Hand plays out normally
3. Client receives seed_hex after hand ends
4. Client verifies: SHA-256(seed_hex) == seed_commitment
5. Client replays: FairRng(seed_bytes).shuffle(deck) == server's deck
```

### New Tests

- `test_fairness.py` (133 lines) — HMAC-DRBG determinism, seed verification, shuffle reproducibility
- `test_game.py` (104 lines) — seed commitment in game state
- `test_dice_game.py` (96 lines) — dice rolls use FairRng
- `test_hand.py` (62 lines) — hand state includes seed

---

## 5. Frontend Deletion

**`packages/nu-front/` deleted entirely** — 95 files, ~5,885 lines. The entire Next.js frontend (leaderboard, games, player stats, spectator UI, narration, hooks) was removed. Replaced with static HTML files in `packages/frontend/` (lobby.html, leaderboard.html, spectator.html).

---

## Summary

| Theme | What Changed |
|-------|-------------|
| **Provable Fairness** | HMAC-DRBG commit-reveal RNG. Clients can replay and verify every hand/round |
| **Attestation** | NSM-based enclave identity proof. Verifiable server Ethereum address |
| **Enclave Infrastructure** | Full Nitro Enclave: Docker, vsock bridges, KMS PCR-0 policy, CI build pipeline |
| **Escrow Security** | PCR-0 binding (settlement locked to enclave code), admin signature verification |
| **Routing** | `/poker/*` → `/game/poker/*`, `/dice/*` → `/game/dice/*`, single ALB wildcard |
| **Skills** | Split into per-game-type files for poker and dice |
| **Frontend** | Deleted Next.js app (nu-front), replaced with static HTML |
