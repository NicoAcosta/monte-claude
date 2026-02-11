# ---------- Secrets Manager ----------

# DB credentials — assembled from RDS outputs
resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "monteclaude/${var.environment}/db-credentials"
  description = "PostgreSQL connection credentials for Monteclaude"
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = aws_db_instance.postgres.username
    password = random_password.db_password.result
    host     = aws_db_instance.postgres.address
    port     = aws_db_instance.postgres.port
    dbname   = var.db_name
    url      = "postgresql://${aws_db_instance.postgres.username}:${random_password.db_password.result}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.db_name}"
  })
}

# Server private key (Ethereum signing)
resource "aws_secretsmanager_secret" "server_private_key" {
  name        = "monteclaude/${var.environment}/server-private-key"
  description = "Ethereum private key for escrow signing"
}

resource "aws_secretsmanager_secret_version" "server_private_key" {
  secret_id     = aws_secretsmanager_secret.server_private_key.id
  secret_string = var.server_private_key
}

# Base chain RPC URL
resource "aws_secretsmanager_secret" "rpc_url" {
  name        = "monteclaude/${var.environment}/rpc-url"
  description = "Base chain RPC endpoint"
}

resource "aws_secretsmanager_secret_version" "rpc_url" {
  secret_id     = aws_secretsmanager_secret.rpc_url.id
  secret_string = var.base_rpc_url
}

# EscrowFactory address
resource "aws_secretsmanager_secret" "factory_address" {
  name        = "monteclaude/${var.environment}/factory-address"
  description = "Deployed EscrowFactory contract address"
}

resource "aws_secretsmanager_secret_version" "factory_address" {
  secret_id     = aws_secretsmanager_secret.factory_address.id
  secret_string = var.factory_address
}

# KMS-encrypted private key (enclave mode only)
# Stores the ciphertext blob — the plaintext is only recoverable inside an attested enclave.
resource "aws_secretsmanager_secret" "server_private_key_encrypted" {
  count = var.enclave_enabled ? 1 : 0

  name        = "monteclaude/${var.environment}/server-private-key-encrypted"
  description = "KMS-encrypted Ethereum private key (decryptable only inside Nitro Enclave)"
}

# The ciphertext is stored manually after encrypting with the KMS key:
#   aws kms encrypt --key-id <arn> --plaintext fileb://key.txt --output text --query CiphertextBlob
# Then put into Secrets Manager via CLI or console. Terraform only creates the secret shell.

# ---------- Per-service env file secrets ----------
# Deploy workflow pulls these at deploy time and writes to /etc/monteclaude/<svc>.env.
# Composed from existing Terraform values so rotation is a single terraform apply + redeploy.

locals {
  db_url = "postgresql://${aws_db_instance.postgres.username}:${random_password.db_password.result}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.db_name}"
}

resource "aws_secretsmanager_secret" "game_api_env" {
  name        = "monteclaude/${var.environment}/game-api-env"
  description = "Game API environment variables"
}

resource "aws_secretsmanager_secret_version" "game_api_env" {
  secret_id = aws_secretsmanager_secret.game_api_env.id
  secret_string = join("\n", [
    "DATABASE_URL=${local.db_url}",
    "SERVER_PRIVATE_KEY=${var.server_private_key}",
    "BASE_RPC_URL=${var.base_rpc_url}",
    "FACTORY_ADDRESS=${var.factory_address}",
    "RAKE_BPS=${var.rake_bps}",
    "RAKE_BENEFICIARY=${var.rake_beneficiary}",
    "CHAIN_ID=${var.chain_id}",
    "LOG_LEVEL=INFO",
  ])
}

resource "aws_secretsmanager_secret" "data_api_env" {
  name        = "monteclaude/${var.environment}/data-api-env"
  description = "Data API environment variables"
}

resource "aws_secretsmanager_secret_version" "data_api_env" {
  secret_id = aws_secretsmanager_secret.data_api_env.id
  secret_string = join("\n", [
    "DATABASE_URL=${local.db_url}",
    "LOG_LEVEL=INFO",
  ])
}

resource "aws_secretsmanager_secret" "account_api_env" {
  name        = "monteclaude/${var.environment}/account-api-env"
  description = "Account API environment variables"
}

resource "aws_secretsmanager_secret_version" "account_api_env" {
  secret_id = aws_secretsmanager_secret.account_api_env.id
  secret_string = join("\n", [
    "DATABASE_URL=${local.db_url}",
    "LOG_LEVEL=INFO",
  ])
}

resource "aws_secretsmanager_secret" "frontend_env" {
  name        = "monteclaude/${var.environment}/frontend-env"
  description = "Frontend environment variables"
}

resource "aws_secretsmanager_secret_version" "frontend_env" {
  secret_id = aws_secretsmanager_secret.frontend_env.id
  secret_string = join("\n", [
    "DATA_API_URL=http://localhost:8000",
    "GAME_API_URL=http://${aws_instance.game_api.private_ip}:8001",
    "NODE_ENV=production",
  ])
}
