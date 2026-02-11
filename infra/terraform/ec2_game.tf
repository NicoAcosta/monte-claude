# ---------- Game API EC2 instance ----------

resource "aws_instance" "game_api" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.game_api_instance_type
  subnet_id              = module.vpc.private_subnets[0]
  iam_instance_profile   = aws_iam_instance_profile.game_api.name
  vpc_security_group_ids = [aws_security_group.app.id]

  # Enable Nitro Enclaves now (costs nothing, needed for Phase 2)
  enclave_options {
    enabled = true
  }

  key_name = var.ssh_key_name != "" ? var.ssh_key_name : null

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = base64encode(
    var.enclave_enabled
    ? templatefile("${path.module}/templates/game_api_userdata_enclave.sh.tpl", {
      aws_region                   = var.aws_region
      ecr_repo                     = aws_ecr_repository.game_api.repository_url
      db_secret_arn                = aws_secretsmanager_secret.db_credentials.arn
      encrypted_privkey_secret_arn = aws_secretsmanager_secret.server_private_key_encrypted[0].arn
      rpc_secret_arn               = aws_secretsmanager_secret.rpc_url.arn
      factory_secret_arn           = aws_secretsmanager_secret.factory_address.arn
      rds_host                     = aws_db_instance.postgres.address
      rpc_host                     = regex("^https?://([^/]+)", var.base_rpc_url)[0]
      kms_key_arn                  = aws_kms_key.enclave[0].arn
      rake_bps                     = var.rake_bps
      rake_beneficiary             = var.rake_beneficiary
      chain_id                     = var.chain_id
    })
    : templatefile("${path.module}/templates/game_api_userdata.sh.tpl", {
      aws_region         = var.aws_region
      ecr_repo           = aws_ecr_repository.game_api.repository_url
      db_secret_arn      = aws_secretsmanager_secret.db_credentials.arn
      privkey_secret_arn = aws_secretsmanager_secret.server_private_key.arn
      rpc_secret_arn     = aws_secretsmanager_secret.rpc_url.arn
      factory_secret_arn = aws_secretsmanager_secret.factory_address.arn
      rake_bps           = var.rake_bps
      rake_beneficiary   = var.rake_beneficiary
      chain_id           = var.chain_id
    })
  )

  tags = { Name = "monteclaude-game-api-${var.environment}" }

  lifecycle {
    # User data changes trigger replacement; use create_before_destroy
    # for zero-downtime redeploys via CI/CD (SSM run command) instead.
    ignore_changes = [user_data, ami]
  }
}
