#!/bin/bash
set -euo pipefail

# --- Install Docker ---
dnf update -y
dnf install -y docker aws-cli jq
systemctl enable docker
systemctl start docker

# --- ECR login ---
aws ecr get-login-password --region ${aws_region} | \
  docker login --username AWS --password-stdin ${ecr_repo}

# --- Fetch secrets and write env file (0600, not visible in process args) ---
DB_URL=$(aws secretsmanager get-secret-value \
  --region ${aws_region} \
  --secret-id ${db_secret_arn} \
  --query 'SecretString' --output text | jq -r '.url')

SERVER_PRIVATE_KEY=$(aws secretsmanager get-secret-value \
  --region ${aws_region} \
  --secret-id ${privkey_secret_arn} \
  --query 'SecretString' --output text)

BASE_RPC_URL=$(aws secretsmanager get-secret-value \
  --region ${aws_region} \
  --secret-id ${rpc_secret_arn} \
  --query 'SecretString' --output text)

FACTORY_ADDRESS=$(aws secretsmanager get-secret-value \
  --region ${aws_region} \
  --secret-id ${factory_secret_arn} \
  --query 'SecretString' --output text)

mkdir -p /etc/monteclaude
cat > /etc/monteclaude/game-api.env <<EOF
DATABASE_URL=$DB_URL
SERVER_PRIVATE_KEY=$SERVER_PRIVATE_KEY
BASE_RPC_URL=$BASE_RPC_URL
FACTORY_ADDRESS=$FACTORY_ADDRESS
RAKE_BPS=${rake_bps}
RAKE_BENEFICIARY=${rake_beneficiary}
CHAIN_ID=${chain_id}
LOG_LEVEL=INFO
EOF
chmod 0600 /etc/monteclaude/game-api.env

# --- Run Game API container ---
docker pull ${ecr_repo}:latest

docker run -d \
  --name game-api \
  --restart unless-stopped \
  -p 8001:8001 \
  --env-file /etc/monteclaude/game-api.env \
  ${ecr_repo}:latest
