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

mkdir -p /etc/monteclaude
cat > /etc/monteclaude/data-api.env <<EOF
DATABASE_URL=$DB_URL
LOG_LEVEL=INFO
EOF
chmod 0600 /etc/monteclaude/data-api.env

# --- Run Data API container ---
docker pull ${ecr_repo}:latest

docker run -d \
  --name data-api \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file /etc/monteclaude/data-api.env \
  ${ecr_repo}:latest
