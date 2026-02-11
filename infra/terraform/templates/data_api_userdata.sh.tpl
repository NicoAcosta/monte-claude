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

# --- Fetch secrets and write env files (0600, not visible in process args) ---
DB_URL=$(aws secretsmanager get-secret-value \
  --region ${aws_region} \
  --secret-id ${db_secret_arn} \
  --query 'SecretString' --output text | jq -r '.url')

mkdir -p /etc/monteclaude

cat > /etc/monteclaude/data-api.env <<EOF
DATABASE_URL=$DB_URL
LOG_LEVEL=INFO
EOF
chmod 0600 /etc/monteclaude/data-api.env

# Account API uses the same DB credentials
cat > /etc/monteclaude/account-api.env <<EOF
DATABASE_URL=$DB_URL
LOG_LEVEL=INFO
EOF
chmod 0600 /etc/monteclaude/account-api.env

# --- Run Data API container ---
docker pull ${ecr_repo}:latest

docker run -d \
  --name data-api \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file /etc/monteclaude/data-api.env \
  ${ecr_repo}:latest

# --- Run Account API container (co-located) ---
docker pull ${account_api_ecr_repo}:latest

docker run -d \
  --name account-api \
  --restart unless-stopped \
  -p 8002:8002 \
  --env-file /etc/monteclaude/account-api.env \
  ${account_api_ecr_repo}:latest

# --- Run Frontend container (co-located, --network host for localhost:8000 access) ---
cat > /etc/monteclaude/frontend.env <<EOF
DATA_API_URL=http://localhost:8000
GAME_API_URL=http://${game_api_private_ip}:8001
NODE_ENV=production
EOF
chmod 0600 /etc/monteclaude/frontend.env

docker pull ${frontend_ecr_repo}:latest

docker run -d \
  --name frontend \
  --restart unless-stopped \
  --network host \
  --env-file /etc/monteclaude/frontend.env \
  ${frontend_ecr_repo}:latest
