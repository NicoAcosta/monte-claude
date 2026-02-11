# ---------- RDS PostgreSQL ----------

resource "aws_db_subnet_group" "postgres" {
  name       = "monteclaude-db-${var.environment}"
  subnet_ids = module.vpc.database_subnets
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "aws_db_instance" "postgres" {
  identifier = "monteclaude-${var.environment}"

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 5
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = "monteclaude"
  password = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.db.id]

  publicly_accessible       = false
  multi_az                  = false
  skip_final_snapshot       = false
  final_snapshot_identifier = "monteclaude-${var.environment}-final"

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  performance_insights_enabled = true

  tags = { Name = "monteclaude-${var.environment}" }
}
