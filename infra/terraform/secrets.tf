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
