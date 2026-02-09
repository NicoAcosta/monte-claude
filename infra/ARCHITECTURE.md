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
                     └───┬───────┬───┘
                         │       │
           ┌─────────────┘       └─────────────┐
           │                                   │
    ┌──────┴──────┐                     ┌──────┴──────┐
    │  Game API   │                     │  Data API   │
    │ c6a.xlarge  │                     │  t3.small   │
    │  Port 8001  │                     │  Port 8000  │
    │  1 worker   │                     │  4 workers  │
    │  (private)  │                     │  (private)  │
    └──────┬──────┘                     └──────┬──────┘
           │                                   │
           └─────────────┐       ┌─────────────┘
                         │       │
                    ┌────┴───────┴────┐
                    │  RDS PostgreSQL │
                    │   db.t3.medium  │
                    │   Port 5432    │
                    │   (database    │
                    │    subnet)     │
                    └────────────────┘
```

The system runs two FastAPI applications sharing one PostgreSQL database. They are deployed as Docker containers on separate EC2 instances behind a single ALB.

| Component | Purpose | Instance | Why |
|-----------|---------|----------|-----|
| **Game API** | Writes + live state reads | c6a.xlarge | Nitro Enclave-capable; game state is in-memory (single worker) |
| **Data API** | Read-only queries + static HTML | t3.small | Scales horizontally (4 uvicorn workers); no access to signing keys |
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
              443,80       8000,8001     5432
```

| SG | Inbound | Outbound |
|----|---------|----------|
| **ALB** | 443/tcp, 80/tcp from `0.0.0.0/0` | 8000-8001/tcp to App SG |
| **App** | 8000/tcp, 8001/tcp from ALB SG | 5432/tcp to DB SG; 443/tcp, 80/tcp to `0.0.0.0/0` (RPC, ECR, SSM) |
| **DB** | 5432/tcp from App SG only | None |

Cross-SG rules use separate `aws_vpc_security_group_*_rule` resources to avoid Terraform circular dependencies.

---

## Load Balancer & Routing

The ALB performs path-based routing to split traffic between Game API and Data API. **The default action sends everything to the Data API.** Specific rules forward write endpoints and live-state reads to the Game API.

### Listener Modes

| Mode | Condition | Listeners |
|------|-----------|-----------|
| **HTTP-only** | `domain_name = ""` | Port 80 → forward to Data API |
| **HTTPS** | `domain_name` set | Port 443 (TLS) → forward to Data API; Port 80 → 301 redirect to HTTPS |

Set `domain_name` in `terraform.tfvars` to switch from HTTP to HTTPS. An ACM certificate is created automatically; DNS validation records must be added manually (or via Route 53 once the hosted zone exists).

### Routing Rules

Rules are evaluated in priority order. Lower number = higher priority. Gaps between priorities allow inserting new rules without reordering.

| Priority | Method | Path Pattern | Target |
|----------|--------|-------------|--------|
| 100 | POST | `/api/register` | Game API |
| 200 | POST | `/api/games` | Game API |
| 300 | POST | `/api/faucet` | Game API |
| 400 | GET | `/game/*/state`, `/game/*/spectator`, `/game/*/waiting`, `/game/*/escrow`, `/game/*/funding` | Game API |
| 410 | GET | `/game/*/settlement`, `/game/*/offchain-settlement` | Game API |
| 500 | POST | `/game/*` | Game API |
| 600 | POST | `/stream/*` | Game API |
| 610 | GET | `/stream/*/data` | Game API |
| Default | Any | Everything else | Data API |

**Key routing invariants:**
- `GET /api/games` (list games) → Data API. `POST /api/games` (create game) → Game API. Method condition differentiates them.
- `GET /game/{id}/streams` (list streams for game) → Data API (falls through to default). `POST /game/{id}/streams` (create stream) → Game API (caught by priority 500).
- All `/game/*` POST traffic is caught by the priority 500 wildcard rule. This covers join, start, action, resign, chat, extend, and stream creation.

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

### Data API (t3.small)

| Property | Value |
|----------|-------|
| Instance type | `t3.small` (2 vCPU, 2 GB RAM) |
| Subnet | Private (no public IP) |
| Root volume | 20 GB gp3, encrypted |
| Workers | 4 (read-only, horizontally scalable) |
| Docker port | 8000 |

The Data API is strictly read-only. It queries PostgreSQL for historical data and serves static HTML files. Each uvicorn worker has its own in-process TTL cache (lobby 3s, leaderboard 15s, stats 30s).

### Secret Injection

Secrets are fetched from AWS Secrets Manager at instance boot time and written to `/etc/monteclaude/<api>.env` (mode `0600`). Docker containers read these via `--env-file`. This approach:

- Keeps secrets out of Docker process arguments (not visible in `ps` or `/proc`)
- Persists across container restarts (env file survives `docker restart`)
- Doesn't require application-level Secrets Manager integration

The env files are created by the EC2 user data script on first boot and reused by the CI/CD deploy workflow on subsequent deployments.

| Env File | Variables |
|----------|-----------|
| `/etc/monteclaude/game-api.env` | `DATABASE_URL`, `SERVER_PRIVATE_KEY`, `BASE_RPC_URL`, `FACTORY_ADDRESS`, `RAKE_BPS`, `RAKE_BENEFICIARY`, `CHAIN_ID`, `LOG_LEVEL` |
| `/etc/monteclaude/data-api.env` | `DATABASE_URL`, `LOG_LEVEL` |

The Data API has **no access** to `SERVER_PRIVATE_KEY`, `BASE_RPC_URL`, or `FACTORY_ADDRESS` — neither via IAM (Secrets Manager policy) nor via env file.

---

## Docker Images

Both images are built from the repo root with context `.` and stored in Amazon ECR.

### Game API (`infra/docker/Dockerfile.game`)

```
python:3.11-slim → libpq5 → uv → install deps → copy src → uvicorn (port 8001, 1 worker)
```

### Data API (`infra/docker/Dockerfile.data`)

```
python:3.11-slim → libpq5 → uv → install deps → copy src → copy frontend to /frontend/ → copy instructions.md to / → uvicorn (port 8000, 4 workers)
```

**Path resolution note:** The Data API resolves static file paths relative to its source file location:
- `STATIC_DIR = Path(__file__).parent.parent.parent.parent / "frontend"` → `/frontend/`
- `INSTRUCTIONS_PATH = Path(__file__).parent.parent.parent.parent.parent / "instructions.md"` → `/instructions.md`

This is why frontend files are copied to `/frontend/` (root) and not `/app/frontend/`.

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

| Role | Secrets Access | Other Permissions |
|------|---------------|-------------------|
| Game API | All 4 secrets | ECR pull (scoped to monteclaude repos), SSM, CloudWatch |
| Data API | `db-credentials` only | ECR pull (scoped to monteclaude repos), SSM, CloudWatch |

ECR image-pull permissions are scoped to `monteclaude/game-api` and `monteclaude/data-api` repos only (not `*`).

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

**Build job:** Builds both Docker images, tags them with the git SHA and `latest`, pushes to ECR.

**Deploy job:** Uses SSM Run Command (not SSH) to deploy. Each instance:
1. Logs into ECR
2. Pulls the new image
3. Stops and removes the old container
4. Starts the new container with `--env-file /etc/monteclaude/<api>.env`

**Health check:** Verifies both APIs are reachable through the ALB. Data API is checked via `GET /ping`. Game API is checked by hitting a routed GET endpoint and verifying the response is not 502/503.

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

The Game API is designed to move inside a Nitro Enclave, providing hardware-level isolation. The operator cannot inspect game state, card order, or the signing key at runtime.

### Architecture Change

```
┌─────────────────────────────────────────┐
│  EC2 Instance (c6a.xlarge)              │
│                                         │
│  ┌────────────────────────────────────┐ │
│  │  Nitro Enclave                     │ │
│  │  ┌──────────────────────────────┐  │ │
│  │  │  Game API (uvicorn :8001)    │  │ │
│  │  │  SERVER_PRIVATE_KEY in mem   │  │ │
│  │  └──────────────────────────────┘  │ │
│  │          ↕ vsock (CID 16)          │ │
│  └────────────────────────────────────┘ │
│                                         │
│  ┌─────────────────┐                   │
│  │  Vsock proxy     │                   │
│  │  ALB ↔ vsock     │                   │
│  │  vsock ↔ RDS     │                   │
│  │  vsock ↔ RPC     │                   │
│  └─────────────────┘                   │
└─────────────────────────────────────────┘
```

Enclaves have **zero networking**. All traffic flows through vsock:
- **Inbound:** ALB → parent EC2 → vsock proxy → enclave (HTTP requests)
- **Outbound:** Enclave → vsock → parent EC2 → TCP (DB connections, RPC calls)

### Key Management

The `SERVER_PRIVATE_KEY` is encrypted with a KMS key whose policy only allows decryption from within an attested enclave (matching PCR-0). The decrypted key only ever exists in enclave memory.

### Phase 2 Files

- `infra/docker/Dockerfile.game.enclave` — amazonlinux-based image for enclave compatibility
- `.github/workflows/build-eif.yml` — Builds the Enclave Image File (EIF), outputs PCR values

### Phase 3: Attestation

A `GET /attestation` endpoint will return a COSE-signed attestation document from the Nitro Secure Module. Players can verify:

1. Clone the repo and build the EIF locally (reproducible build)
2. Compare local PCR values against the attestation document
3. If they match, the server is running the exact published code

---

## Cost Breakdown

| Resource | Spec | Monthly Cost |
|----------|------|-------------|
| EC2 (Game API) | c6a.xlarge, on-demand | ~$110 |
| EC2 (Data API) | t3.small, on-demand | ~$15 |
| RDS PostgreSQL | db.t3.medium, single-AZ | ~$50 |
| ALB | Standard | ~$20 |
| NAT Instance | t3.nano | ~$4 |
| ECR | Image storage | ~$2 |
| Secrets Manager | 4 secrets | ~$2 |
| WAF | Standard rules | ~$10 |
| **Total** | | **~$213/mo** |

Switching the Game API to a 1-year Reserved Instance would save ~$43/mo.

---

## File Reference

```
infra/
├── terraform/
│   ├── main.tf                 # Provider, S3 backend
│   ├── variables.tf            # All input variables
│   ├── outputs.tf              # ALB DNS, RDS endpoint, instance IDs
│   ├── vpc.tf                  # VPC, subnets, NAT instance
│   ├── alb.tf                  # ALB, listeners, routing rules, ACM
│   ├── rds.tf                  # PostgreSQL 16 instance
│   ├── ec2_game.tf             # Game API EC2
│   ├── ec2_data.tf             # Data API EC2
│   ├── security_groups.tf      # 3-tier SG chain
│   ├── secrets.tf              # Secrets Manager entries
│   ├── iam.tf                  # Roles, policies, ECR repos
│   ├── waf.tf                  # WAF rules
│   ├── terraform.tfvars.example# Template for actual values
│   └── templates/
│       ├── game_api_userdata.sh.tpl  # EC2 bootstrap for Game API
│       └── data_api_userdata.sh.tpl  # EC2 bootstrap for Data API
├── docker/
│   ├── Dockerfile.game         # Game API container
│   └── Dockerfile.data         # Data API container
└── scripts/
    └── init-db.sh              # One-time schema initialization

.github/workflows/
├── deploy.yml                  # CI/CD: test → build → push → deploy
└── build-eif.yml               # Phase 2: Enclave image build (placeholder)
```
