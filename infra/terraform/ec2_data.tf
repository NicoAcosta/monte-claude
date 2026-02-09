# ---------- Data API EC2 instance ----------

resource "aws_instance" "data_api" {
  ami                  = data.aws_ami.amazon_linux.id
  instance_type        = var.data_api_instance_type
  subnet_id            = module.vpc.private_subnets[0]
  iam_instance_profile = aws_iam_instance_profile.data_api.name
  vpc_security_group_ids = [aws_security_group.app.id]

  key_name = var.ssh_key_name != "" ? var.ssh_key_name : null

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = base64encode(templatefile("${path.module}/templates/data_api_userdata.sh.tpl", {
    aws_region           = var.aws_region
    ecr_repo             = aws_ecr_repository.data_api.repository_url
    account_api_ecr_repo = aws_ecr_repository.account_api.repository_url
    db_secret_arn        = aws_secretsmanager_secret.db_credentials.arn
  }))

  tags = { Name = "monteclaude-data-api-${var.environment}" }

  lifecycle {
    ignore_changes = [user_data, ami]
  }
}
