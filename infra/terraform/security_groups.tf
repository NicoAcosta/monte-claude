# SG chain: Internet → ALB → App → DB
# Uses separate rule resources to avoid circular dependency between SGs.

# ---------- ALB Security Group ----------

resource "aws_security_group" "alb" {
  name_prefix = "monteclaude-alb-"
  description = "ALB - public HTTPS ingress"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP redirect"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------- App Security Group (Game API + Data API + Account API) ----------

resource "aws_security_group" "app" {
  name_prefix = "monteclaude-app-"
  description = "App tier - Game API (8001) + Data API (8000) + Account API (8002)"
  vpc_id      = module.vpc.vpc_id

  egress {
    description = "HTTPS outbound (RPC calls, ECR, Secrets Manager, SSM)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "HTTP outbound (package installs)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------- Database Security Group ----------

resource "aws_security_group" "db" {
  name_prefix = "monteclaude-db-"
  description = "RDS - PostgreSQL from app tier only"
  vpc_id      = module.vpc.vpc_id
}

# ---------- Cross-SG rules (avoids circular dependencies) ----------

# ALB → App (egress: backend services 8000-8002)
resource "aws_vpc_security_group_egress_rule" "alb_to_app" {
  security_group_id            = aws_security_group.alb.id
  description                  = "To app instances (Game 8001, Data 8000, Account 8002)"
  from_port                    = 8000
  to_port                      = 8002
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.app.id
}

# ALB → App (egress: frontend 3000)
resource "aws_vpc_security_group_egress_rule" "alb_to_frontend" {
  security_group_id            = aws_security_group.alb.id
  description                  = "Frontend from ALB"
  from_port                    = 3000
  to_port                      = 3000
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.app.id
}

# App ← ALB (ingress: Game API)
resource "aws_vpc_security_group_ingress_rule" "app_from_alb_game" {
  security_group_id            = aws_security_group.app.id
  description                  = "Game API from ALB"
  from_port                    = 8001
  to_port                      = 8001
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.alb.id
}

# App ← ALB (ingress: Data API)
resource "aws_vpc_security_group_ingress_rule" "app_from_alb_data" {
  security_group_id            = aws_security_group.app.id
  description                  = "Data API from ALB"
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.alb.id
}

# App ← ALB (ingress: Account API — co-located on Data API EC2)
resource "aws_vpc_security_group_ingress_rule" "app_from_alb_account" {
  security_group_id            = aws_security_group.app.id
  description                  = "Account API from ALB"
  from_port                    = 8002
  to_port                      = 8002
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.alb.id
}

# App ← ALB (ingress: Frontend)
resource "aws_vpc_security_group_ingress_rule" "app_from_alb_frontend" {
  security_group_id            = aws_security_group.app.id
  description                  = "Frontend from ALB"
  from_port                    = 3000
  to_port                      = 3000
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.alb.id
}

# App → DB (egress)
resource "aws_vpc_security_group_egress_rule" "app_to_db" {
  security_group_id            = aws_security_group.app.id
  description                  = "PostgreSQL to DB"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.db.id
}

# DB ← App (ingress)
resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = aws_security_group.db.id
  description                  = "PostgreSQL from app tier"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.app.id
}
