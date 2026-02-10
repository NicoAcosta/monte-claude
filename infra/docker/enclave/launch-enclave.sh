#!/bin/bash
# Parent-side enclave launcher — runs on the EC2 host.
#
# Responsibilities:
#   1. Start vsock-proxy instances (DB, HTTPS for KMS+RPC)
#   2. Launch the Nitro Enclave from the EIF
#   3. Send config + encrypted key to the enclave via vsock port 9000
#   4. Start inbound socat bridge (ALB TCP:8001 → VSOCK:CID:8001)
#
# Usage: launch-enclave.sh <eif-path> <config-json-path>
#   eif-path:        Path to the built .eif file
#   config-json-path: Path to JSON config file for the enclave
set -euo pipefail

EIF_PATH="${1:?Usage: launch-enclave.sh <eif-path> <config-json-path>}"
CONFIG_PATH="${2:?Usage: launch-enclave.sh <eif-path> <config-json-path>}"

ENCLAVE_CPU=2
ENCLAVE_MEM=4096
ENCLAVE_CID=16

echo "[launcher] Starting enclave deployment"

# --- 1. Start vsock-proxy for outbound connections ---
# These run on the parent and forward vsock connections from the enclave
# to real TCP endpoints.

# Kill any existing vsock-proxy instances
pkill -f vsock-proxy || true
sleep 1

# DB proxy: enclave vsock:3:5432 → TCP to RDS
RDS_HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_PATH'))['rds_host'])")
vsock-proxy 5432 "$RDS_HOST" 5432 --config /etc/nitro_enclaves/vsock-proxy.yaml &
echo "[launcher] vsock-proxy: 5432 → $RDS_HOST:5432"

# HTTPS proxy: enclave vsock:3:443 → TCP to allowlisted hosts (KMS, RPC)
vsock-proxy 443 0.0.0.0 443 --config /etc/nitro_enclaves/vsock-proxy.yaml &
echo "[launcher] vsock-proxy: 443 → allowlisted HTTPS hosts"

# KMS proxy: enclave vsock:3:8000 → TCP to KMS endpoint
KMS_REGION=$(python3 -c "import json; print(json.load(open('$CONFIG_PATH'))['kms_region'])")
vsock-proxy 8000 "kms.${KMS_REGION}.amazonaws.com" 443 &
echo "[launcher] vsock-proxy: 8000 → kms.${KMS_REGION}.amazonaws.com:443"

sleep 2

# --- 2. Terminate existing enclave if running ---
EXISTING=$(nitro-cli describe-enclaves | python3 -c "
import sys, json
enclaves = json.load(sys.stdin)
for e in enclaves:
    if e.get('State') == 'RUNNING':
        print(e['EnclaveID'])
" 2>/dev/null || true)

if [ -n "$EXISTING" ]; then
  echo "[launcher] Terminating existing enclave: $EXISTING"
  nitro-cli terminate-enclave --enclave-id "$EXISTING"
  sleep 2
fi

# --- 3. Launch enclave ---
echo "[launcher] Launching enclave from $EIF_PATH (${ENCLAVE_CPU} vCPU, ${ENCLAVE_MEM} MB)"
LAUNCH_OUTPUT=$(nitro-cli run-enclave \
  --eif-path "$EIF_PATH" \
  --cpu-count "$ENCLAVE_CPU" \
  --memory "$ENCLAVE_MEM" \
  --enclave-cid "$ENCLAVE_CID")

echo "$LAUNCH_OUTPUT"

ENCLAVE_ID=$(echo "$LAUNCH_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['EnclaveID'])")
echo "[launcher] Enclave started: $ENCLAVE_ID"

# Wait for enclave to be ready
sleep 3

# --- 4. Send config to enclave via vsock port 9000 ---
echo "[launcher] Sending config to enclave on vsock CID $ENCLAVE_CID port 9000"

# Fetch temporary credentials from instance metadata (IMDSv2)
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
ROLE_NAME=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/security-credentials/)
CREDS=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" "http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE_NAME")

AWS_ACCESS_KEY_ID=$(echo "$CREDS" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKeyId'])")
AWS_SECRET_ACCESS_KEY=$(echo "$CREDS" | python3 -c "import sys,json; print(json.load(sys.stdin)['SecretAccessKey'])")
AWS_SESSION_TOKEN=$(echo "$CREDS" | python3 -c "import sys,json; print(json.load(sys.stdin)['Token'])")

# Merge credentials into the config
FULL_CONFIG=$(python3 -c "
import json
config = json.load(open('$CONFIG_PATH'))
config['aws_access_key_id'] = '$AWS_ACCESS_KEY_ID'
config['aws_secret_access_key'] = '$AWS_SECRET_ACCESS_KEY'
config['aws_session_token'] = '$AWS_SESSION_TOKEN'
print(json.dumps(config))
")

echo "$FULL_CONFIG" | socat -t 10 STDIN VSOCK-CONNECT:${ENCLAVE_CID}:9000
echo "[launcher] Config sent to enclave"

# --- 5. Start inbound socat bridge ---
# Forward HTTP from ALB (TCP:8001) to enclave (VSOCK:CID:8001)
# Kill any existing inbound bridge
pkill -f "socat.*TCP-LISTEN:8001" || true
sleep 1

socat TCP-LISTEN:8001,reuseaddr,fork VSOCK-CONNECT:${ENCLAVE_CID}:8001 &
echo "[launcher] Inbound bridge: tcp:8001 → vsock:${ENCLAVE_CID}:8001"

# --- 6. Verify ---
sleep 5
echo "[launcher] Checking enclave status..."
nitro-cli describe-enclaves

echo "[launcher] Enclave deployment complete"
echo "[launcher] Game API should be reachable on localhost:8001"
