#!/bin/bash
# Game API EC2 user data — ENCLAVE MODE
#
# This script runs on first boot when enclave_enabled=true.
# It sets up the parent EC2 as a Nitro Enclave host:
#   1. Install Docker, nitro-enclaves-cli, socat
#   2. Configure the Nitro Enclaves allocator (CPU + memory)
#   3. Write vsock-proxy allowlist
#   4. Pull the Game API Docker image from ECR
#   5. Build the EIF (Enclave Image File)
#   6. Fetch encrypted private key from Secrets Manager
#   7. Assemble config JSON and launch the enclave
set -euo pipefail

exec > /var/log/enclave-setup.log 2>&1
echo "[userdata] Enclave setup starting at $(date)"

# --- 1. Install packages ---
dnf update -y
dnf install -y docker aws-cli jq aws-nitro-enclaves-cli aws-nitro-enclaves-cli-devel socat

systemctl enable docker
systemctl start docker
systemctl enable nitro-enclaves-allocator

# --- 2. Configure Nitro Enclaves allocator ---
# Reserve 2 vCPU + 4096 MB for the enclave (out of 4 vCPU + 8 GB on c6a.xlarge)
cat > /etc/nitro_enclaves/allocator.yaml <<EOF
---
memory_mib: 4096
cpu_count: 2
EOF

systemctl restart nitro-enclaves-allocator
echo "[userdata] Allocator configured: 2 vCPU, 4096 MB"

# --- 3. vsock-proxy allowlist ---
# The vsock-proxy only forwards connections to hosts in this list.
cat > /etc/nitro_enclaves/vsock-proxy.yaml <<EOF
allowlist:
  - {address: "${rds_host}", port: 5432}
  - {address: "kms.${aws_region}.amazonaws.com", port: 443}
  - {address: "${rpc_host}", port: 443}
EOF
echo "[userdata] vsock-proxy allowlist written"

# --- 4. ECR login + pull image ---
aws ecr get-login-password --region ${aws_region} | \
  docker login --username AWS --password-stdin ${ecr_repo}

docker pull ${ecr_repo}:latest
echo "[userdata] Docker image pulled"

# --- 5. Build EIF from Docker image ---
nitro-cli build-enclave \
  --docker-uri ${ecr_repo}:latest \
  --output-file /opt/monteclaude/game-api.eif

echo "[userdata] EIF built at /opt/monteclaude/game-api.eif"

# --- 6. Fetch secrets ---
DB_URL=$(aws secretsmanager get-secret-value \
  --region ${aws_region} \
  --secret-id ${db_secret_arn} \
  --query 'SecretString' --output text | jq -r '.url')

ENCRYPTED_KEY=$(aws secretsmanager get-secret-value \
  --region ${aws_region} \
  --secret-id ${encrypted_privkey_secret_arn} \
  --query 'SecretString' --output text)

RPC_URL=$(aws secretsmanager get-secret-value \
  --region ${aws_region} \
  --secret-id ${rpc_secret_arn} \
  --query 'SecretString' --output text)

FACTORY_ADDR=$(aws secretsmanager get-secret-value \
  --region ${aws_region} \
  --secret-id ${factory_secret_arn} \
  --query 'SecretString' --output text)

# --- 7. Assemble config JSON ---
mkdir -p /opt/monteclaude
cat > /opt/monteclaude/enclave-config.json <<EOF
{
  "rds_host": "${rds_host}",
  "rpc_host": "${rpc_host}",
  "kms_region": "${aws_region}",
  "kms_key_id": "${kms_key_arn}",
  "encrypted_key": "$ENCRYPTED_KEY",
  "db_url": "$DB_URL",
  "rpc_url": "$RPC_URL",
  "factory_address": "$FACTORY_ADDR",
  "rake_bps": "${rake_bps}",
  "rake_beneficiary": "${rake_beneficiary}",
  "chain_id": "${chain_id}"
}
EOF
chmod 0600 /opt/monteclaude/enclave-config.json

# --- 8. Write launch script (self-contained, embedded in user data) ---
cat > /opt/monteclaude/launch-enclave.sh <<'LAUNCH_SCRIPT'
#!/bin/bash
set -euo pipefail

EIF_PATH="${1:?Usage: launch-enclave.sh <eif-path> <config-json-path>}"
CONFIG_PATH="${2:?Usage: launch-enclave.sh <eif-path> <config-json-path>}"

ENCLAVE_CPU=2
ENCLAVE_MEM=4096
ENCLAVE_CID=16

echo "[launcher] Starting enclave deployment"

# Kill existing vsock-proxy and bridges
pkill -f vsock-proxy || true
pkill -f "socat.*TCP-LISTEN:8001" || true
sleep 1

# DB proxy
RDS_HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_PATH'))['rds_host'])")
vsock-proxy 5432 "$RDS_HOST" 5432 --config /etc/nitro_enclaves/vsock-proxy.yaml &

# HTTPS proxy (for RPC)
vsock-proxy 443 0.0.0.0 443 --config /etc/nitro_enclaves/vsock-proxy.yaml &

# KMS proxy
KMS_REGION=$(python3 -c "import json; print(json.load(open('$CONFIG_PATH'))['kms_region'])")
vsock-proxy 8000 "kms.${KMS_REGION}.amazonaws.com" 443 &

sleep 2

# Terminate existing enclave
EXISTING=$(nitro-cli describe-enclaves | python3 -c "
import sys, json
for e in json.load(sys.stdin):
    if e.get('State') == 'RUNNING':
        print(e['EnclaveID'])
" 2>/dev/null || true)

if [ -n "$EXISTING" ]; then
  nitro-cli terminate-enclave --enclave-id "$EXISTING"
  sleep 2
fi

# Launch enclave
LAUNCH_OUTPUT=$(nitro-cli run-enclave \
  --eif-path "$EIF_PATH" \
  --cpu-count "$ENCLAVE_CPU" \
  --memory "$ENCLAVE_MEM" \
  --enclave-cid "$ENCLAVE_CID")

echo "$LAUNCH_OUTPUT"
sleep 3

# Send config with instance credentials
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
ROLE_NAME=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/security-credentials/)
CREDS=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" "http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE_NAME")

FULL_CONFIG=$(python3 -c "
import json
config = json.load(open('$CONFIG_PATH'))
creds = json.loads('''$(echo "$CREDS")''')
config['aws_access_key_id'] = creds['AccessKeyId']
config['aws_secret_access_key'] = creds['SecretAccessKey']
config['aws_session_token'] = creds['Token']
print(json.dumps(config))
")

echo "$FULL_CONFIG" | socat -t 10 STDIN VSOCK-CONNECT:${ENCLAVE_CID}:9000

# Inbound bridge: ALB TCP:8001 → enclave VSOCK:8001
socat TCP-LISTEN:8001,reuseaddr,fork VSOCK-CONNECT:${ENCLAVE_CID}:8001 &

sleep 5
nitro-cli describe-enclaves
echo "[launcher] Enclave deployment complete"
LAUNCH_SCRIPT
chmod +x /opt/monteclaude/launch-enclave.sh

# --- 9. Launch ---
/opt/monteclaude/launch-enclave.sh \
  /opt/monteclaude/game-api.eif \
  /opt/monteclaude/enclave-config.json

echo "[userdata] Enclave setup complete at $(date)"
