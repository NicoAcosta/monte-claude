#!/bin/bash
# Enclave entrypoint — runs INSIDE the Nitro Enclave.
#
# Lifecycle:
#   1. Bring up loopback interface (no networking by default in enclaves)
#   2. Receive JSON config from parent via vsock port 9000
#   3. Start socat bridges (inbound HTTP, outbound DB + HTTPS + KMS)
#   4. Write /etc/hosts entries so TLS SNI works through socat tunnels
#   5. Decrypt SERVER_PRIVATE_KEY via KMS attestation (kmstool_enclave_cli)
#   6. Exec uvicorn
set -euo pipefail

echo "[init] Enclave entrypoint starting"

# --- 1. Loopback ---
ip link set dev lo up || true

# --- 2. Receive config from parent via vsock ---
# Parent sends JSON blob to vsock port 9000 immediately after enclave starts.
# Format: {"rds_host":"...","rpc_host":"...","kms_region":"...","kms_key_id":"...","encrypted_key":"...","db_url":"...","rpc_url":"...","factory_address":"...","rake_bps":"...","rake_beneficiary":"...","chain_id":"..."}
echo "[init] Waiting for config on vsock port 9000..."
CONFIG=$(socat -t 30 VSOCK-LISTEN:9000,reuseaddr STDOUT)

if [ -z "$CONFIG" ]; then
  echo "[init] ERROR: No config received on vsock port 9000"
  exit 1
fi
echo "[init] Config received"

# Parse config values
rds_host=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['rds_host'])")
rpc_host=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['rpc_host'])")
kms_region=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['kms_region'])")
kms_key_id=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['kms_key_id'])")
encrypted_key=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['encrypted_key'])")
db_url=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['db_url'])")
rpc_url=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['rpc_url'])")
factory_address=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['factory_address'])")
rake_bps=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['rake_bps'])")
rake_beneficiary=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['rake_beneficiary'])")
chain_id=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['chain_id'])")
kms_endpoint=$(echo "$CONFIG" | python3 -c "
import sys, json
c = json.load(sys.stdin)
print(c.get('kms_endpoint', f\"kms.{c['kms_region']}.amazonaws.com\"))
")

# --- 3. Start socat bridges ---
# These must be running before KMS decrypt (kmstool needs port 8000 bridge)

# Inbound: VSOCK-LISTEN:8001 → forward to local uvicorn on 127.0.0.1:8001
socat VSOCK-LISTEN:8001,reuseaddr,fork TCP-CONNECT:127.0.0.1:8001 &
echo "[init] Inbound bridge: vsock:8001 → tcp:127.0.0.1:8001"

# Outbound DB: listen on TCP:5432, forward through vsock to parent CID 3 port 5432
socat TCP-LISTEN:5432,reuseaddr,fork,bind=127.0.0.1 VSOCK-CONNECT:3:5432 &
echo "[init] Outbound DB bridge: tcp:127.0.0.1:5432 → vsock:3:5432"

# Outbound HTTPS: listen on TCP:443, forward through vsock to parent CID 3 port 443
socat TCP-LISTEN:443,reuseaddr,fork,bind=127.0.0.1 VSOCK-CONNECT:3:443 &
echo "[init] Outbound HTTPS bridge: tcp:127.0.0.1:443 → vsock:3:443"

# Outbound KMS: listen on TCP:8000, forward through vsock to parent CID 3 port 8000
# kmstool_enclave_cli uses --proxy-port 8000 to reach KMS
socat TCP-LISTEN:8000,reuseaddr,fork,bind=127.0.0.1 VSOCK-CONNECT:3:8000 &
echo "[init] Outbound KMS bridge: tcp:127.0.0.1:8000 → vsock:3:8000"

sleep 1

# --- 4. DNS via /etc/hosts ---
# Enclave has no DNS resolver. Map real hostnames to 127.0.0.1 so the app
# connects to localhost socat, which tunnels through vsock to the parent.
# TLS SNI uses the hostname, so certificate validation works.
echo "127.0.0.1 $rds_host" >> /etc/hosts
echo "127.0.0.1 $rpc_host" >> /etc/hosts
echo "127.0.0.1 $kms_endpoint" >> /etc/hosts
echo "[init] DNS entries written to /etc/hosts"

# --- 5. KMS decrypt ---
# kmstool_enclave_cli sends attestation document to KMS, which validates PCR-0
# before releasing the plaintext. The decrypted key exists only in enclave memory.
echo "[init] Decrypting SERVER_PRIVATE_KEY via KMS attestation..."
export AWS_DEFAULT_REGION="$kms_region"

SERVER_PRIVATE_KEY=$(echo "$encrypted_key" | base64 -d | \
  kmstool_enclave_cli decrypt \
    --region "$kms_region" \
    --proxy-port 8000 \
    --aws-access-key-id "$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['aws_access_key_id'])")" \
    --aws-secret-access-key "$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['aws_secret_access_key'])")" \
    --aws-session-token "$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin)['aws_session_token'])")" \
    --ciphertext /dev/stdin 2>/dev/null)

if [ -z "$SERVER_PRIVATE_KEY" ]; then
  echo "[init] ERROR: KMS decryption failed"
  exit 1
fi
echo "[init] KMS decryption successful"

# --- 6. Start Game API ---
echo "[init] Starting uvicorn..."
export DATABASE_URL="$db_url"
export SERVER_PRIVATE_KEY
export BASE_RPC_URL="$rpc_url"
export FACTORY_ADDRESS="$factory_address"
export RAKE_BPS="$rake_bps"
export RAKE_BENEFICIARY="$rake_beneficiary"
export CHAIN_ID="$chain_id"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

exec python3 -m uvicorn game_api.app:app --host 127.0.0.1 --port 8001
