#!/usr/bin/env bash
# setup-test-game.sh — Start Anvil, deploy contracts, seed wallets, start server, create a funded game.
#
# Usage:
#   ./scripts/setup-test-game.sh [NUM_PLAYERS]
#
# Defaults to 3 players. Outputs a JSON summary with all keys/IDs needed to connect agents.
# Requires: anvil, forge, cast, curl, jq, uv (all from Foundry + Python tooling)

set -uo pipefail

# ── Config ───────────────────────────────────────────────
NUM_PLAYERS="${1:-3}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_DIR="$REPO_ROOT/packages/server"
CONTRACTS_DIR="$REPO_ROOT/packages/contracts"

BASE_RPC="https://lb.routeme.sh/rpc/8453/3bd2e340-f97c-46b3-80ed-17975de5af89"
BUY_IN="1000000000000000000000"  # 1000 MONTE (18 decimals)
ANVIL_PORT=8545
SERVER_PORT=8000
RPC="http://localhost:$ANVIL_PORT"
SERVER="http://localhost:$SERVER_PORT"

# Anvil default accounts (standard mnemonic)
ADMIN_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ADMIN_ADDR="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

PRIVATE_KEYS=(
  "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
  "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"
  "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6"
  "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a"
  "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba"
  "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e"
  "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356"
  "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97"
)

WALLETS=(
  "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
  "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
  "0x90F79bf6EB2c4f870365E785982E1f101E93b906"
  "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"
  "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"
  "0x976EA74026E726554dB657fA54763abd0C3a0aa9"
  "0x14dC79964da2C08dA15Fd353d30d9cBd31045526"
  "0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f"
)

PLAYER_NAMES=("Wild Bill" "The Professor" "Lady Luck" "Maverick" "Snake Eyes" "Doc Holiday" "Calamity Jane" "The Kid")

if (( NUM_PLAYERS > 8 )); then
  echo "Error: max 8 players supported (Anvil account limit)"
  exit 1
fi

# ── Helpers ──────────────────────────────────────────────
log() { echo "[$1] $2"; }
die() { echo "ERROR: $1" >&2; exit 1; }

cleanup() {
  log "CLEANUP" "Stopping background processes..."
  lsof -ti:$SERVER_PORT | xargs kill -9 2>/dev/null || true
  lsof -ti:$ANVIL_PORT  | xargs kill -9 2>/dev/null || true
}

wait_for_rpc() {
  local port=$1 max_wait=${2:-20} elapsed=0
  while ! cast chain-id --rpc-url "http://localhost:$port" >/dev/null 2>&1; do
    sleep 0.5
    elapsed=$((elapsed + 1))
    (( elapsed >= max_wait * 2 )) && die "RPC on port $port not ready after ${max_wait}s"
  done
}

wait_for_http() {
  local port=$1 max_wait=${2:-15} elapsed=0
  while ! curl -sf "http://localhost:$port/api/games" >/dev/null 2>&1; do
    sleep 0.5
    elapsed=$((elapsed + 1))
    (( elapsed >= max_wait * 2 )) && die "HTTP on port $port not ready after ${max_wait}s"
  done
}

# ── Step 1: Kill existing processes ──────────────────────
log "SETUP" "Cleaning up existing processes on ports $ANVIL_PORT and $SERVER_PORT..."
for port in $SERVER_PORT $ANVIL_PORT; do
  PIDS=$(lsof -ti:"$port" 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs kill -9 2>/dev/null || true
  fi
done
sleep 2

# ── Step 2: Start Anvil forking Base ────────────────────
log "ANVIL" "Starting Anvil fork of Base mainnet..."
anvil --fork-url "$BASE_RPC" --port $ANVIL_PORT --silent &
ANVIL_PID=$!
wait_for_rpc $ANVIL_PORT 20
log "ANVIL" "Running on port $ANVIL_PORT (PID: $ANVIL_PID)"

# ── Step 3: Install forge deps if missing ────────────────
if [ ! -d "$CONTRACTS_DIR/lib/forge-std" ]; then
  log "FORGE" "Installing dependencies..."
  (cd "$CONTRACTS_DIR" && forge install foundry-rs/forge-std OpenZeppelin/openzeppelin-contracts Vectorized/solady --no-git 2>&1 | tail -3)
fi

# ── Step 4: Deploy MonteClaudio token + EscrowFactory ────
log "DEPLOY" "Deploying MonteClaudio (MONTE) token..."
MONTE_OUTPUT=$(cd "$CONTRACTS_DIR" && forge create src/MonteClaudio.sol:MonteClaudio \
  --rpc-url "$RPC" --private-key "$ADMIN_KEY" --broadcast 2>&1)
MONTE_ADDRESS=$(echo "$MONTE_OUTPUT" | grep "Deployed to:" | awk '{print $NF}')
[ -z "$MONTE_ADDRESS" ] && die "Failed to parse MONTE address from deploy output"
log "DEPLOY" "MonteClaudio (MONTE): $MONTE_ADDRESS"

log "DEPLOY" "Deploying EscrowFactory..."
DEPLOY_OUTPUT=$(cd "$CONTRACTS_DIR" && forge script script/Deploy.s.sol \
  --rpc-url "$RPC" --private-key "$ADMIN_KEY" --broadcast 2>&1)

FACTORY_ADDRESS=$(echo "$DEPLOY_OUTPUT" | grep "EscrowFactory:" | awk '{print $NF}')
[ -z "$FACTORY_ADDRESS" ] && die "Failed to parse factory address from deploy output"
log "DEPLOY" "EscrowFactory: $FACTORY_ADDRESS"

# ── Step 5: Claim MONTE from faucet for player wallets ───
log "MONTE" "Claiming 10,000 MONTE per player from faucet..."
for i in $(seq 0 $((NUM_PLAYERS - 1))); do
  cast send "$MONTE_ADDRESS" "faucet()" \
    --private-key "${PRIVATE_KEYS[$i]}" --rpc-url "$RPC" >/dev/null 2>&1
done
log "MONTE" "Done"

# ── Step 6: Set up Python venv if needed ────────────────
if [ ! -d "$SERVER_DIR/.venv" ]; then
  log "PYTHON" "Creating venv and installing deps..."
  (cd "$SERVER_DIR" && uv venv && uv pip install -e ".[dev]" 2>&1 | tail -1)
fi

# Clear persistent data from previous sessions
log "DATA" "Clearing previous session data..."
rm -f "$SERVER_DIR"/data/*.csv 2>/dev/null || true

# ── Step 7: Start poker server ──────────────────────────
log "SERVER" "Starting poker server on port $SERVER_PORT..."
(cd "$SERVER_DIR" && \
  SERVER_PRIVATE_KEY="$ADMIN_KEY" \
  BASE_RPC_URL="$RPC" \
  FACTORY_ADDRESS="$FACTORY_ADDRESS" \
  RAKE_BPS=250 \
  RAKE_BENEFICIARY="$ADMIN_ADDR" \
  CHAIN_ID=8453 \
  FUNDING_TIMEOUT=600 \
  SETTLEMENT_TIMEOUT=7200 \
  .venv/bin/uvicorn poker.server:app --host 0.0.0.0 --port $SERVER_PORT &) 2>/dev/null
wait_for_http $SERVER_PORT 15
log "SERVER" "Running on port $SERVER_PORT"

# ── Step 8: Create funded game ──────────────────────────
log "GAME" "Creating funded game for $NUM_PLAYERS players (buy-in: 1000 MONTE)..."
GAME_RESP=$(curl -s -X POST "$SERVER/api/games" \
  -H "Content-Type: application/json" \
  -d "{\"max_players\": $NUM_PLAYERS, \"token\": \"$MONTE_ADDRESS\", \"buy_in\": $BUY_IN, \"token_decimals\": 18, \"token_symbol\": \"MONTE\"}")
GAME_ID=$(echo "$GAME_RESP" | jq -r .game_id)
log "GAME" "Game ID: $GAME_ID"

# ── Step 9: Register players + commentator, join game ───
declare -a API_KEYS=()
declare -a PLAYER_IDS=()

for i in $(seq 0 $((NUM_PLAYERS - 1))); do
  NAME="${PLAYER_NAMES[$i]}"
  REG=$(curl -s -X POST "$SERVER/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"username\": \"$NAME\"}")
  KEY=$(echo "$REG" | jq -r .api_key)
  API_KEYS+=("$KEY")

  JOIN=$(curl -s -X POST "$SERVER/game/$GAME_ID/join" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $KEY" \
    -d "{\"wallet_address\": \"${WALLETS[$i]}\"}")
  PID=$(echo "$JOIN" | jq -r .player_id)
  PLAYER_IDS+=("$PID")
  log "PLAYER" "Registered '$NAME' (id=$PID)"
done

# Register commentator
COMM_REG=$(curl -s -X POST "$SERVER/api/register" \
  -H "Content-Type: application/json" \
  -d '{"username": "PokerCast"}')
COMM_KEY=$(echo "$COMM_REG" | jq -r .api_key)
log "PLAYER" "Registered commentator 'PokerCast'"

# ── Step 10: Fund escrow ────────────────────────────────
log "ESCROW" "Fetching escrow info..."
ESCROW_INFO=$(curl -s "$SERVER/game/$GAME_ID/escrow")
ESCROW_ADDR=$(echo "$ESCROW_INFO" | jq -r .escrow_address)
CALLDATA_CREATE=$(echo "$ESCROW_INFO" | jq -r .calldata_create_and_deposit)
log "ESCROW" "Escrow address: $ESCROW_ADDR"

# First player: approve factory + createAndDeposit
log "ESCROW" "Player 1 depositing (createAndDeposit)..."
cast send "$MONTE_ADDRESS" "approve(address,uint256)" "$FACTORY_ADDRESS" "$BUY_IN" \
  --private-key "${PRIVATE_KEYS[0]}" --rpc-url "$RPC" >/dev/null 2>&1
cast send "$FACTORY_ADDRESS" "$CALLDATA_CREATE" \
  --private-key "${PRIVATE_KEYS[0]}" --rpc-url "$RPC" >/dev/null 2>&1

# Remaining players: approve escrow + deposit
for i in $(seq 1 $((NUM_PLAYERS - 1))); do
  CALLDATA=$(echo "$ESCROW_INFO" | jq -r ".calldata_deposit[\"${WALLETS[$i]}\"]")
  log "ESCROW" "Player $((i+1)) depositing..."
  cast send "$MONTE_ADDRESS" "approve(address,uint256)" "$ESCROW_ADDR" "$BUY_IN" \
    --private-key "${PRIVATE_KEYS[$i]}" --rpc-url "$RPC" >/dev/null 2>&1
  cast send "$ESCROW_ADDR" "$CALLDATA" \
    --private-key "${PRIVATE_KEYS[$i]}" --rpc-url "$RPC" >/dev/null 2>&1
done

# Verify all deposited
FUNDING=$(curl -s "$SERVER/game/$GAME_ID/funding")
ALL_DEP=$(echo "$FUNDING" | jq -r .all_deposited)
[ "$ALL_DEP" != "true" ] && die "Not all deposits confirmed: $FUNDING"
log "ESCROW" "All deposits confirmed"

# ── Step 11: Start game ─────────────────────────────────
log "GAME" "Starting game..."
START_RESP=$(curl -s -X POST "$SERVER/game/$GAME_ID/start" -H "X-API-Key: ${API_KEYS[0]}")
log "GAME" "$(echo "$START_RESP" | jq -r .message)"

# ── Step 12: Create commentary stream ───────────────────
STREAM_RESP=$(curl -s -X POST "$SERVER/game/$GAME_ID/streams" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $COMM_KEY" \
  -d '{"title": "PokerCast Live"}')
STREAM_ID=$(echo "$STREAM_RESP" | jq -r .stream_id)
log "STREAM" "Stream ID: $STREAM_ID"

# ── Output summary ──────────────────────────────────────
echo ""
echo "=============================================="
echo "  GAME READY"
echo "=============================================="
echo ""
echo "Server:     $SERVER"
echo "Game ID:    $GAME_ID"
echo "Escrow:     $ESCROW_ADDR"
echo "Stream ID:  $STREAM_ID"
echo ""
echo "Spectator UI:  $SERVER/game/$GAME_ID"
echo "Stream UI:     $SERVER/stream/$STREAM_ID"
echo ""

# Build JSON output
PLAYERS_JSON="["
for i in $(seq 0 $((NUM_PLAYERS - 1))); do
  [ $i -gt 0 ] && PLAYERS_JSON+=","
  PLAYERS_JSON+="{\"name\":\"${PLAYER_NAMES[$i]}\",\"id\":${PLAYER_IDS[$i]},\"api_key\":\"${API_KEYS[$i]}\",\"wallet\":\"${WALLETS[$i]}\"}"
done
PLAYERS_JSON+="]"

SUMMARY=$(jq -n \
  --arg server "$SERVER" \
  --argjson game_id "$GAME_ID" \
  --arg monte "$MONTE_ADDRESS" \
  --arg escrow "$ESCROW_ADDR" \
  --argjson stream_id "$STREAM_ID" \
  --arg comm_key "$COMM_KEY" \
  --argjson players "$PLAYERS_JSON" \
  '{server: $server, game_id: $game_id, monte_address: $monte, escrow_address: $escrow, stream_id: $stream_id, commentator_key: $comm_key, players: $players}')

echo "Players:"
echo "$SUMMARY" | jq -r '.players[] | "  \(.name) (id=\(.id)) key=\(.api_key)"'
echo ""
echo "Commentator key: $COMM_KEY"
echo ""

# Write summary to file for agents to read
SUMMARY_FILE="$REPO_ROOT/.game-session.json"
echo "$SUMMARY" > "$SUMMARY_FILE"
echo "Session saved to: $SUMMARY_FILE"
echo ""
echo "To stop everything: lsof -ti:$SERVER_PORT -ti:$ANVIL_PORT | xargs kill"
echo "=============================================="
