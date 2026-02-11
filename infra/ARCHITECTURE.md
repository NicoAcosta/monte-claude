# Monteclaude Cloud Infrastructure

Production deployment of the Monteclaude poker server on AWS, with a path to Nitro Enclave-based provably fair gaming.

## Overview

```
                          Internet
                             │
                        ┌────┴────┐
                        │   WAF   │  Rate limit + OWASP rules
                        └────┬────┘
                             │
                     ┌───────┴───────┐
                     │  ALB (public) │  TLS termination, path-based routing
                     │  Port 80/443  │
                     └──┬────┬───┬──┘
                        │    │   │
          ┌─────────────┘    │   └──────────────┐
          │                  │                  │
   ┌──────┴──────┐    ┌─────┴──────┐    ┌──────┴──────┐
   │  Game API   │    │ Account API│    │  Frontend   │
   │ c6a.xlarge  │    │ (co-located│    │  (Next.js)  │
   │  Port 8001  │    │  on Data   │    │  Port 3000  │
   │  1 worker   │    │  API EC2)  │    │  t3.medium  │
   │  (private)  │    │ Port 8002  │    │  (private)  │
   └──────┬──────┘    │  2 workers │    ├─────────────┤
          │           └─────┬──────┘    │  Data API   │
          │                 │           │  Port 8000  │
          │                 │           │  4 workers  │
          │                 │           └──────┬──────┘
          │                 │                  │
          └─────────────┐   │   ┌──────────────┘
                        │   │   │
                   ┌────┴───┴───┴────┐
                   │  RDS PostgreSQL │
                   │   db.t3.medium  │
                   │   Port 5432    │
                   │   (database    │
                   │    subnet)     │
                   └────────────────┘
```

The system runs three FastAPI applications and a Next.js frontend sharing one PostgreSQL database. Game API runs on its own EC2 instance. Frontend, Data API, and Account API are co-located on a shared EC2 instance. All sit behind a single ALB with path-based routing.

| Component | Purpose | Instance | Why |
|-----------|---------|----------|-----|
| **Game API** | Writes + live state reads | c6a.xlarge | Nitro Enclave-capable; game state is in-memory (single worker) |
| **Frontend** | Next.js spectator UI, proxies API calls | t3.medium (shared) | Standalone app; rewrites proxy `/api/*` to backends |
| **Data API** | Read-only API queries | t3.medium (shared) | Scales horizontally (4 uvicorn workers); no access to signing keys |
| **Account API** | Registration, faucet, balance | t3.medium (shared) | Lightweight stateless service (2 workers); co-located with Data API |
| **RDS** | PostgreSQL 16 | db.t3.medium | Shared database for accounts, balances, history, game metadata |

---

## Network Architecture

### VPC Layout

| Subnet Tier | CIDR | AZs | Contains |
|-------------|------|-----|----------|
| **Public** | `10.0.1.0/24`, `10.0.2.0/24` | us-east-1a, 1b | ALB, NAT instance |
| **Private** | `10.0.10.0/24`, `10.0.11.0/24` | us-east-1a, 1b | Game API EC2, Data API EC2 |
| **Database** | `10.0.20.0/24`, `10.0.21.0/24` | us-east-1a, 1b | RDS (no public access) |

VPC CIDR: `10.0.0.0/16`. Managed via `terraform-aws-modules/vpc/aws` v5.

### NAT Instance

Private subnets reach the internet through a `t3.nano` NAT instance (~$4/mo) instead of a managed NAT Gateway (~$35/mo). The instance runs Amazon Linux 2023 with iptables MASQUERADE. Source/dest check is disabled to allow packet forwarding.

If the NAT instance goes down, private-subnet instances lose outbound connectivity (ECR pulls, Secrets Manager access, RPC calls). Restart it via the AWS console or set up a health-check alarm.

### Security Groups

Traffic flows through a strict SG chain. Each tier only accepts traffic from the tier above it — no CIDR blocks between tiers.

```
Internet ──► [ALB SG] ──► [App SG] ──► [DB SG]
              443,80    3000,8000-8002  5432
```

| SG | Inbound | Outbound |
|----|---------|----------|
| **ALB** | 443/tcp, 80/tcp from `0.0.0.0/0` | 3000/tcp, 8000-8002/tcp to App SG |
| **App** | 3000/tcp, 8000/tcp, 8001/tcp, 8002/tcp from ALB SG | 5432/tcp to DB SG; 443/tcp, 80/tcp to `0.0.0.0/0` (RPC, ECR, SSM) |
| **DB** | 5432/tcp from App SG only | None |

Cross-SG rules use separate `aws_vpc_security_group_*_rule` resources to avoid Terraform circular dependencies.

---

## Load Balancer & Routing

The ALB performs path-based routing to split traffic between the Frontend, Game API, and Data API. **The default action sends everything to the Frontend** (port 3000). Specific rules forward write endpoints, WebSocket connections, and live-state reads to the Game API. The Next.js frontend proxies `/api/*` calls to the correct backend via `next.config.ts` rewrites.

### Listener Modes

| Mode | Condition | Listeners |
|------|-----------|-----------|
| **HTTP-only** | `domain_name = ""` | Port 80 → forward to Frontend |
| **HTTPS** | `domain_name` set | Port 443 (TLS) → forward to Frontend; Port 80 → 301 redirect to HTTPS |

Set `domain_name` in `terraform.tfvars` to switch from HTTP to HTTPS. An ACM certificate is created automatically; DNS validation records must be added manually (or via Route 53 once the hosted zone exists).

### Routing Rules

Rules are evaluated in priority order. Lower number = higher priority. Gaps between priorities allow inserting new rules without reordering.

| Priority | Method | Path Pattern | Target |
|----------|--------|-------------|--------|
| 100 | POST | `/api/register` | Account API |
| 150 | Any | `/admin/*` | Game API |
| 200 | Any | `/game/*` | Game API |
| 250 | Any | `/ws/*` | Game API (WebSocket) |
| 300 | POST | `/api/faucet` | Account API |
| 350 | GET | `/api/balance` | Account API |
| 400 | POST | `/stream/*` | Game API |
| 410 | GET | `/stream/*/data` | Game API |
| 450 | GET | `/attestation*` | Game API |
| Default | Any | Everything else | Frontend |

All game traffic is routed by a single `/game/*` wildcard. Game-type routes live at `/game/poker/*`, `/game/dice/*`, etc. Adding a new game type requires **no terraform changes** — just mount the router in Python. Toggling a game on/off is an app-level concern; the ALB routes regardless and the Game API returns an error for paused games.

**Key routing invariants:**
- `POST /api/register`, `POST /api/faucet`, `GET /api/balance` → Account API. Served by the Account API co-located on the Data API EC2.
- `/api/*` calls from the browser → Frontend (default) → Next.js rewrites proxy to Data API or Game API as appropriate.
- `GET /api/games` (list games) → Data API (proxied by Next.js). `POST /game/poker/games` / `POST /game/dice/games` (create) → Game API (caught by `/game/*`).
- `GET /api/games/{id}/streams` (list streams) → Data API (proxied by Next.js). `POST /game/{id}/streams` (create stream) → Game API (caught by `/game/*`).
- `/ws/*` → Game API (WebSocket connections for real-time game state).
- `/attestation*` → Game API (Nitro Enclave attestation endpoint).
- All game-type traffic (`/game/poker/*`, `/game/dice/*`) and game-agnostic traffic (`/game/{id}/spectator`, `/game/{id}/streams`) is caught by the single priority 200 rule.

### Health Checks

Both target groups use `GET /ping` with 15-second intervals. The `/ping` endpoint returns `{"status": "ok"}` with no database dependency (fast, no false negatives from DB hiccups). The more detailed `/health` endpoint (DB ping + pool stats) is available but not used for ALB health checks to avoid flapping.

---

## Database

### RDS Configuration

| Setting | Value |
|---------|-------|
| Engine | PostgreSQL 16 |
| Instance | `db.t3.medium` (2 vCPU, 4 GB) |
| Storage | 20 GB gp3, auto-scales to 100 GB |
| Encryption | At rest (AES-256, AWS-managed key) |
| Multi-AZ | No (single-AZ for cost) |
| Backups | 7-day retention, daily at 03:00-04:00 UTC |
| Maintenance | Sundays 04:00-05:00 UTC |
| Performance Insights | Enabled |
| Public access | No |
| Final snapshot | Required before deletion |

### Schema Initialization

The schema is **not** applied automatically by Terraform. After `terraform apply`, run the init script once:

```bash
# From an SSM session on one of the EC2 instances:
export DATABASE_URL="postgresql://monteclaude:<password>@<rds-endpoint>:5432/monteclaude"
psql "$DATABASE_URL" -f /path/to/packages/server/db/init.sql
```

Or use the helper script:

```bash
./infra/scripts/init-db.sh "postgresql://monteclaude:<password>@<rds-endpoint>:5432/monteclaude"
```

The connection string is stored in Secrets Manager at `monteclaude/<env>/db-credentials` (JSON with a `url` field).

### Schema Changes

Schema changes are managed via `packages/server/db/init.sql`. To apply changes:

1. Update `init.sql` with additive migrations (new tables, new columns, new indexes)
2. Run the changed statements against RDS via `psql`
3. **Never drop tables** — project policy forbids destructive schema changes

---

## Compute

### Game API (c6a.xlarge)

| Property | Value |
|----------|-------|
| Instance type | `c6a.xlarge` (4 vCPU, 8 GB RAM) |
| Subnet | Private (no public IP) |
| Nitro Enclaves | Enabled (for Phase 2 TEE) |
| Root volume | 30 GB gp3, encrypted |
| Workers | 1 (game state is in-memory, single authority) |
| Docker port | 8001 |

The Game API is the **single source of truth** for live game state. It must run as a single worker — multiple workers would create split-brain problems since game state lives in Python process memory.

**Why c6a.xlarge?** It's the cheapest instance type that supports Nitro Enclaves. Enclave support is enabled now (costs nothing) so we don't need to replace the instance for Phase 2.

### Data API + Account API + Frontend (t3.medium, co-located)

| Property | Value |
|----------|-------|
| Instance type | `t3.medium` (2 vCPU, 4 GB RAM) |
| Subnet | Private (no public IP) |
| Root volume | 20 GB gp3, encrypted |
| Containers | 3 (Frontend + Data API + Account API) |
| Docker ports | 3000 (Frontend), 8000 (Data API), 8002 (Account API) |

This EC2 instance runs three Docker containers:

**Frontend** (port 3000, `--network host`): Next.js standalone app serving the spectator UI and all HTML pages. Proxies `/api/*` calls to the appropriate backend via `next.config.ts` rewrites. Built with `NEXT_PUBLIC_GAME_WS_URL=wss://monteclaude.ai` for WebSocket connections.

**Data API** (port 8000, 4 workers): Strictly read-only API service. Queries PostgreSQL for historical data. Each uvicorn worker has its own in-process TTL cache (lobby 3s, leaderboard 15s, stats 30s). No longer serves static HTML files — the Frontend handles all HTML rendering.

**Account API** (port 8002, 2 workers): Handles user registration, faucet claims, and balance queries. Stateless — all state lives in PostgreSQL. Co-located here because it's lightweight and doesn't need its own instance.

### Secret Injection

Secrets are fetched from AWS Secrets Manager at instance boot time and written to `/etc/monteclaude/<api>.env` (mode `0600`). Docker containers read these via `--env-file`. This approach:

- Keeps secrets out of Docker process arguments (not visible in `ps` or `/proc`)
- Persists across container restarts (env file survives `docker restart`)
- Doesn't require application-level Secrets Manager integration

The env files are created by the EC2 user data script on first boot and reused by the CI/CD deploy workflow on subsequent deployments.

| Env File | Variables | EC2 Instance |
|----------|-----------|-------------|
| `/etc/monteclaude/game-api.env` | `DATABASE_URL`, `SERVER_PRIVATE_KEY`, `BASE_RPC_URL`, `FACTORY_ADDRESS`, `RAKE_BPS`, `RAKE_BENEFICIARY`, `CHAIN_ID`, `LOG_LEVEL` | Game API EC2 |
| `/etc/monteclaude/data-api.env` | `DATABASE_URL`, `LOG_LEVEL` | Data API EC2 |
| `/etc/monteclaude/account-api.env` | `DATABASE_URL`, `LOG_LEVEL` | Data API EC2 |
| `/etc/monteclaude/frontend.env` | `DATA_API_URL`, `GAME_API_URL`, `NODE_ENV` | Data API EC2 |

Neither the Data API nor the Account API have access to `SERVER_PRIVATE_KEY`, `BASE_RPC_URL`, or `FACTORY_ADDRESS` — neither via IAM (Secrets Manager policy) nor via env file.

---

## Docker Images

All four images are built from the repo root with context `.` and stored in Amazon ECR.

### Game API (`infra/docker/Dockerfile.game`)

```
python:3.11-slim → libpq5 → uv → install deps → copy src → uvicorn (port 8001, 1 worker)
```

### Data API (`infra/docker/Dockerfile.data`)

```
python:3.11-slim → libpq5 → uv → install deps → copy src → copy play-monteclaude.md skill → uvicorn (port 8000, 4 workers)
```

The Data API is purely an API service — it no longer serves static HTML files. The `play-monteclaude.md` skill file is copied for the `/api/play` endpoint.

### Frontend (`infra/docker/Dockerfile.frontend`)

```
node:20-alpine → install deps → next build (standalone) → copy .next/standalone + static + public → node server.js (port 3000)
```

Built with `--build-arg NEXT_PUBLIC_GAME_WS_URL=wss://monteclaude.ai` to configure the WebSocket endpoint at build time. Runs with `--network host` on the Data API EC2.

### Account API (`infra/docker/Dockerfile.account`)

```
python:3.11-slim → libpq5 → uv → install deps → copy src → uvicorn (port 8002, 2 workers)
```

No frontend files needed — purely an API service.

### ECR Lifecycle

- Untagged images expire after 7 days
- Only the 10 most recent tagged images are kept
- Images are scanned for vulnerabilities on push

---

## Secrets Management

All secrets live in AWS Secrets Manager under the path `monteclaude/<environment>/`.

| Secret | Contents | Consumers |
|--------|----------|-----------|
| `db-credentials` | JSON: `{username, password, host, port, dbname, url}` | Game API, Data API |
| `server-private-key` | Hex private key for Ethereum signing | Game API only |
| `rpc-url` | Base chain RPC endpoint | Game API only |
| `factory-address` | Deployed EscrowFactory contract address | Game API only |

The RDS password is generated by Terraform (`random_password`, 32 chars, no special chars) and stored in Secrets Manager automatically. **Never** set the password manually — Terraform owns it.

### IAM Access Control

| Role | Secrets Access | ECR Pull | Other Permissions |
|------|---------------|----------|-------------------|
| Game API | All 4 secrets | `monteclaude/game-api` only | SSM, CloudWatch |
| Data API | `db-credentials` only | `monteclaude/data-api` + `monteclaude/account-api` + `monteclaude/frontend` | SSM, CloudWatch |
| GitHub Deploy | None (SM) | All `monteclaude/*` repos (push) | SSM `SendCommand` for deploy |

The Data API role pulls its own image, the Account API image, and the Frontend image (all co-located on the same EC2). ECR permissions are scoped to specific repos (not `*`).

The GitHub Deploy role (`monteclaude-github-deploy`) is assumed via OIDC (`aws_iam_openid_connect_provider` for GitHub Actions) and has permissions to push images to ECR and send SSM commands for deployment.

---

## WAF

The AWS WAF sits in front of the ALB with two rule groups:

| Rule | Priority | Action | Details |
|------|----------|--------|---------|
| AWS Managed Common Rules | 1 | Monitor | SQLi, XSS, and other OWASP protections via `AWSManagedRulesCommonRuleSet` |
| IP Rate Limiting | 2 | Block | 2000 requests per 5-minute window per IP |

Both rules emit CloudWatch metrics for monitoring. The rate limit is configurable via `var.waf_rate_limit`.

---

## CI/CD

### Pipeline (`.github/workflows/deploy.yml`)

Triggered on push to `main` when server, frontend, Docker, or instruction files change. Also supports manual dispatch.

```
┌──────┐     ┌───────────────┐     ┌──────────────┐     ┌──────────────┐
│ Test │────►│ Build & Push  │────►│ Deploy via   │────►│ Health Check │
│      │     │ to ECR        │     │ SSM          │     │              │
└──────┘     └───────────────┘     └──────────────┘     └──────────────┘
  pytest       docker build          ssm send-command     curl /ping
  (postgres    docker push           stop old container   verify 2xx
   service)                          start new container
```

**Test job:** Runs the full pytest suite against a PostgreSQL 16 service container. Schema is applied via `psql` before tests run.

**Build job:** Builds all four Docker images (Game API, Data API, Account API, Frontend), tags them with the git SHA and `latest`, pushes to ECR. The Frontend image is built with `--build-arg NEXT_PUBLIC_GAME_WS_URL=wss://monteclaude.ai`.

**Deploy job:** Uses SSM Run Command (not SSH) to deploy. Two SSM commands:
- **Game API EC2:** Pull game-api image, restart container
- **Data API EC2:** Pull data-api, account-api, and frontend images, restart all three containers

Each container uses `--env-file /etc/monteclaude/<api>.env`.

**Health check:** Verifies all three APIs are reachable through the ALB. Data API is checked via `GET /ping`. Game API is checked by hitting a routed GET endpoint and verifying the response is not 502/503. Account API is checked via `GET /api/balance`.

### Required GitHub Secrets

| Secret | Description | Source |
|--------|-------------|--------|
| `AWS_DEPLOY_ROLE_ARN` | IAM role ARN for OIDC-based AWS auth | Create manually in AWS |
| `GAME_API_INSTANCE_ID` | EC2 instance ID | `terraform output game_api_instance_id` |
| `DATA_API_INSTANCE_ID` | EC2 instance ID | `terraform output data_api_instance_id` |
| `ALB_DNS_NAME` | ALB DNS name | `terraform output alb_dns_name` |
| `ALB_SCHEME` | `http` or `https` (default: `http`) | Set based on domain config |

---

## Deployment Runbook

### First-Time Setup

1. **Bootstrap Terraform backend** (one-time, manual):
   ```bash
   aws s3 mb s3://monteclaude-terraform-state --region us-east-1
   aws dynamodb create-table \
     --table-name monteclaude-terraform-locks \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST \
     --region us-east-1
   ```

2. **Configure variables:**
   ```bash
   cd infra/terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with real values (never commit this file)
   ```

3. **Deploy infrastructure:**
   ```bash
   terraform init
   terraform plan        # Review changes
   terraform apply       # Create resources
   ```

4. **Initialize database:**
   ```bash
   # Get the DATABASE_URL from Secrets Manager or terraform output
   ./infra/scripts/init-db.sh "$DATABASE_URL"
   ```

5. **Set GitHub Secrets** using Terraform outputs:
   ```bash
   terraform output game_api_instance_id
   terraform output data_api_instance_id
   terraform output alb_dns_name
   ```

6. **First deploy:** Push to `main` or trigger the workflow manually.

### Updating Secrets

If you need to rotate a secret (e.g., the Ethereum private key):

1. Update the value in `terraform.tfvars`
2. Run `terraform apply` (updates the Secrets Manager secret)
3. SSH/SSM into the EC2 instance and re-run the secret-fetch section of the user data script, or simply reboot the instance (user data runs on boot)

### Scaling

- **Data API:** Change `data_api_instance_type` to a larger instance, or increase `--workers` in the Dockerfile CMD.
- **Game API:** Cannot add workers (single-authority design). Scale vertically by increasing `game_api_instance_type`.
- **Database:** Change `db_instance_class` for more CPU/RAM, or increase `db_allocated_storage`. Enable Multi-AZ by adding `multi_az = true` to `rds.tf`.

---

## Phase 2: Nitro Enclave (TEE)

**Status: Implemented** (feature-flagged via `enclave_enabled`).

The Game API runs inside a Nitro Enclave, providing hardware-level isolation. The operator cannot inspect game state, card order, or the signing key at runtime. The Python application code is unchanged — this is purely an infrastructure change.

### Architecture (Enclave Mode)

```
PARENT EC2 (c6a.xlarge, 2 vCPU / ~4 GB to parent):
  [socat]        TCP:8001 ←→ VSOCK:CID16:8001     (ALB → enclave)
  [vsock-proxy]  VSOCK:5432 → TCP:RDS:5432          (enclave → DB)
  [vsock-proxy]  VSOCK:443  → TCP:HTTPS:443          (enclave → RPC, allowlisted)
  [vsock-proxy]  VSOCK:8000 → TCP:KMS:443            (enclave → KMS attestation)

ENCLAVE (CID 16, 2 vCPU / 4 GB):
  [socat]        VSOCK-LISTEN:8001 → TCP:127.0.0.1:8001   (inbound HTTP)
  [socat]        TCP-LISTEN:5432   → VSOCK-CONNECT:3:5432  (outbound DB)
  [socat]        TCP-LISTEN:443    → VSOCK-CONNECT:3:443   (outbound HTTPS)
  [kmstool]      Decrypt SERVER_PRIVATE_KEY via KMS attestation
  [uvicorn]      Game API on 127.0.0.1:8001
```

Enclaves have **zero networking**. All traffic flows through vsock:
- **Inbound:** ALB → parent TCP:8001 → socat → VSOCK:CID16:8001 → enclave socat → uvicorn
- **Outbound DB:** uvicorn → TCP:5432 → enclave socat → VSOCK:3:5432 → parent vsock-proxy → RDS
- **Outbound HTTPS:** uvicorn → TCP:443 → enclave socat → VSOCK:3:443 → parent vsock-proxy → RPC/KMS

**DNS inside enclave:** No DNS resolution is available. The init script writes hostnames to `/etc/hosts` pointing to `127.0.0.1`. The app connects to the "real" hostname (TLS SNI works), traffic routes to localhost socat, through vsock, and out via the parent's vsock-proxy.

### Feature Toggle

Set in `terraform.tfvars`:

```hcl
enclave_enabled = false  # Docker mode (default, Phase 1 behavior)
enclave_enabled = true   # Enclave mode (Phase 2)
enclave_pcr0    = "abc123..."  # Required when enclave_enabled=true
```

When `enclave_enabled=false`, no KMS key, encrypted secret, or enclave user data is created. The EC2 boots with the standard Docker user data script. Switching back is instant rollback.

### Private Key Flow (KMS Attestation)

1. `terraform apply` creates a KMS key with policy: `kms:Decrypt` only when `kms:RecipientAttestation:ImageSha384` matches PCR-0
2. Operator encrypts `SERVER_PRIVATE_KEY` with this KMS key, stores ciphertext in Secrets Manager (`server-private-key-encrypted`)
3. At EC2 boot: parent fetches encrypted ciphertext, assembles config JSON
4. Parent launches enclave, sends config (including ciphertext + IAM credentials) via vsock port 9000
5. Enclave calls `kmstool_enclave_cli decrypt` — KMS validates the attestation document's PCR-0
6. Decrypted key only ever exists in enclave memory

### Enclave Deployment

**Initial setup (activation sequence):**

1. Run `build-eif.yml` workflow → note PCR-0 from job summary
2. `terraform apply` with `enclave_enabled=false` first (creates KMS key)
3. Encrypt private key: `aws kms encrypt --key-id <arn> --plaintext fileb://key.txt --output text --query CiphertextBlob`
4. Store ciphertext in Secrets Manager (`monteclaude/<env>/server-private-key-encrypted`)
5. Set `enclave_pcr0=<pcr0>` and `enclave_enabled=true` in `terraform.tfvars`
6. `terraform apply` → EC2 user data switches to enclave mode
7. Reboot Game API EC2 → boots into enclave
8. Verify: `nitro-cli describe-enclaves` via SSM

**Ongoing deploys (CI/CD):** The deploy workflow detects `ENCLAVE_ENABLED` secret. When set, it builds the enclave Dockerfile, pushes to ECR, then SSM commands the EC2 to pull, rebuild EIF, and relaunch the enclave.

**Rollback:** Set `enclave_enabled=false`, `terraform apply`, reboot EC2.

### Enclave Files

| File | Purpose |
|------|---------|
| `infra/docker/Dockerfile.game.enclave` | Multi-stage build: kmstool_enclave_cli + Python runtime |
| `infra/docker/enclave/init.sh` | Enclave entrypoint (loopback, KMS decrypt, socat bridges, uvicorn) |
| `infra/docker/enclave/launch-enclave.sh` | Parent-side launcher (vsock-proxy, nitro-cli, config send, inbound bridge) |
| `infra/terraform/kms.tf` | KMS key with PCR-0 attestation policy |
| `infra/terraform/templates/game_api_userdata_enclave.sh.tpl` | EC2 bootstrap for enclave mode |
| `.github/workflows/build-eif.yml` | Builds EIF, extracts PCR values |

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| 502 from ALB | Enclave not running or socat bridge down | `nitro-cli describe-enclaves` via SSM; check `/var/log/enclave-setup.log` |
| KMS decrypt fails | PCR-0 mismatch (image changed) | Rebuild EIF, update `enclave_pcr0`, `terraform apply` |
| DB connection timeout | vsock-proxy not running | Check `ps aux | grep vsock-proxy` on parent |
| "No config received" in enclave logs | Config send failed | Check socat process on parent, verify CID=16 |
| Enclave OOM | 4 GB not enough | Increase `ENCLAVE_MEM` in launch script (requires larger EC2) |

### Attestation Endpoint

`GET /attestation` on the Game API returns a COSE-signed attestation document from the Nitro Secure Module (NSM). This is the "provably fair" proof — players can verify exactly what code is running.

**How it works:**
1. Game API calls `/dev/nsm` (NSM device) to request an attestation document
2. NSM returns a COSE_Sign1 structure signed by AWS's attestation PKI, containing:
   - PCR-0 (enclave image hash), PCR-1 (kernel), PCR-2 (application)
   - Optional user-supplied nonce (to prevent replay)
3. Response is base64-encoded CBOR

**Player verification flow:**
1. Clone the repo, build the EIF locally → get expected PCR values
2. `GET /attestation?nonce=<random>` → get server's signed attestation
3. Verify COSE signature against AWS Nitro root certificate
4. Compare PCR values — if they match, the server is running the exact published code

**When not running in an enclave** (Docker mode), the endpoint returns HTTP 503 with `{"error": "not running in enclave"}`.

**Implementation:** `packages/server/src/poker/attestation.py` — NSM interaction via `/dev/nsm` ioctl, CBOR encoding via `cbor2` library.

---

## Cost Breakdown

| Resource | Spec | Monthly Cost |
|----------|------|-------------|
| EC2 (Game API) | c6a.xlarge, on-demand | ~$110 |
| EC2 (Data API) | t3.medium, on-demand | ~$30 |
| RDS PostgreSQL | db.t3.medium, single-AZ | ~$50 |
| ALB | Standard | ~$20 |
| NAT Instance | t3.nano | ~$4 |
| ECR | Image storage | ~$2 |
| KMS | Enclave key (if enabled) | ~$1 |
| Secrets Manager | 4-5 secrets | ~$2 |
| WAF | Standard rules | ~$10 |
| **Total** | | **~$229/mo** |

Switching the Game API to a 1-year Reserved Instance would save ~$43/mo.

---

## File Reference

```
infra/
├── terraform/
│   ├── main.tf                 # Provider, S3 backend
│   ├── variables.tf            # All input variables (incl. enclave_enabled, enclave_pcr0)
│   ├── outputs.tf              # ALB DNS, RDS endpoint, instance IDs, KMS ARN, ECR frontend URL, GitHub deploy role ARN, ACM validation records
│   ├── vpc.tf                  # VPC, subnets, NAT instance
│   ├── alb.tf                  # ALB, listeners, routing rules, ACM
│   ├── rds.tf                  # PostgreSQL 16 instance
│   ├── ec2_game.tf             # Game API EC2 (conditional Docker/enclave user data)
│   ├── ec2_data.tf             # Data API EC2
│   ├── security_groups.tf      # 3-tier SG chain
│   ├── secrets.tf              # Secrets Manager entries (incl. encrypted key for enclave)
│   ├── iam.tf                  # Roles, policies, ECR repos, KMS permissions
│   ├── kms.tf                  # KMS key with PCR-0 attestation policy (enclave only)
│   ├── waf.tf                  # WAF rules
│   ├── terraform.tfvars.example# Template for actual values
│   └── templates/
│       ├── game_api_userdata.sh.tpl          # EC2 bootstrap — Docker mode
│       ├── game_api_userdata_enclave.sh.tpl  # EC2 bootstrap — Enclave mode
│       └── data_api_userdata.sh.tpl          # EC2 bootstrap for Data API
├── docker/
│   ├── Dockerfile.game         # Game API container (Docker mode)
│   ├── Dockerfile.game.enclave # Game API container (Enclave mode, amazonlinux + kmstool)
│   ├── Dockerfile.data         # Data API container
│   ├── Dockerfile.frontend     # Frontend container (Next.js, co-located on Data API EC2)
│   ├── Dockerfile.account      # Account API container (co-located on Data API EC2)
│   └── enclave/
│       ├── init.sh             # Enclave entrypoint (loopback, KMS, socat, uvicorn)
│       └── launch-enclave.sh   # Parent-side enclave launcher
└── scripts/
    └── init-db.sh              # One-time schema initialization

.github/workflows/
├── deploy.yml                  # CI/CD: test → build → push → deploy (Docker or enclave)
└── build-eif.yml               # Build EIF + extract PCR values for attestation
```
