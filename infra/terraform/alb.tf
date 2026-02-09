# ---------- Application Load Balancer ----------

locals {
  has_domain        = var.domain_name != ""
  main_listener_arn = local.has_domain ? aws_lb_listener.https[0].arn : aws_lb_listener.http[0].arn
}

resource "aws_lb" "main" {
  name               = "monteclaude-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = module.vpc.public_subnets

  enable_deletion_protection = true
}

# ---------- Target Groups ----------

resource "aws_lb_target_group" "game_api" {
  name     = "mc-game-${var.environment}"
  port     = 8001
  protocol = "HTTP"
  vpc_id   = module.vpc.vpc_id

  health_check {
    path                = "/ping"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200"
  }
}

resource "aws_lb_target_group" "data_api" {
  name     = "mc-data-${var.environment}"
  port     = 8000
  protocol = "HTTP"
  vpc_id   = module.vpc.vpc_id

  health_check {
    path                = "/ping"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200"
  }
}

resource "aws_lb_target_group" "account_api" {
  name     = "mc-account-${var.environment}"
  port     = 8002
  protocol = "HTTP"
  vpc_id   = module.vpc.vpc_id

  health_check {
    path                = "/ping"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200"
  }
}

resource "aws_lb_target_group_attachment" "game_api" {
  target_group_arn = aws_lb_target_group.game_api.arn
  target_id        = aws_instance.game_api.id
  port             = 8001
}

resource "aws_lb_target_group_attachment" "data_api" {
  target_group_arn = aws_lb_target_group.data_api.arn
  target_id        = aws_instance.data_api.id
  port             = 8000
}

# Account API runs co-located on the Data API EC2 instance
resource "aws_lb_target_group_attachment" "account_api" {
  target_group_arn = aws_lb_target_group.account_api.arn
  target_id        = aws_instance.data_api.id
  port             = 8002
}

# ---------- ACM certificate (only when domain is provided) ----------

resource "aws_acm_certificate" "main" {
  count             = local.has_domain ? 1 : 0
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# NOTE: DNS validation records must be created manually (or via Route53 resource
# if zone_id is known). After adding DNS records, Terraform will pick up the
# validated cert on next apply. Add aws_acm_certificate_validation + Route53
# records when the domain and zone are finalized.

# ---------- Listeners ----------

# When domain is set: HTTPS listener with TLS + HTTP→HTTPS redirect.
# When no domain: HTTP-only listener (for initial testing with ALB DNS name).

resource "aws_lb_listener" "https" {
  count             = local.has_domain ? 1 : 0
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.main[0].arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.data_api.arn
  }
}

resource "aws_lb_listener" "http_redirect" {
  count             = local.has_domain ? 1 : 0
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# HTTP-only mode (no domain / initial testing)
resource "aws_lb_listener" "http" {
  count             = local.has_domain ? 0 : 1
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.data_api.arn
  }
}

# ---------- ALB Routing Rules ----------
# Account API handles: register, faucet, balance
# Game API handles: game creation, game POST endpoints, live state reads, spectator, streams
# Data API handles: everything else (default action above)

# Rule 1: POST /api/register → Account API
resource "aws_lb_listener_rule" "account_register" {
  listener_arn = local.main_listener_arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.account_api.arn
  }

  condition {
    path_pattern { values = ["/api/register"] }
  }

  condition {
    http_request_method { values = ["POST"] }
  }
}

# Rule 2: POST /api/games → Game API
resource "aws_lb_listener_rule" "game_create" {
  listener_arn = local.main_listener_arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.game_api.arn
  }

  condition {
    path_pattern { values = ["/api/games"] }
  }

  condition {
    http_request_method { values = ["POST"] }
  }
}

# Rule 3: POST /api/faucet → Account API
resource "aws_lb_listener_rule" "account_faucet" {
  listener_arn = local.main_listener_arn
  priority     = 300

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.account_api.arn
  }

  condition {
    path_pattern { values = ["/api/faucet"] }
  }

  condition {
    http_request_method { values = ["POST"] }
  }
}

# Rule 3b: GET /api/balance → Account API
resource "aws_lb_listener_rule" "account_balance" {
  listener_arn = local.main_listener_arn
  priority     = 350

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.account_api.arn
  }

  condition {
    path_pattern { values = ["/api/balance"] }
  }

  condition {
    http_request_method { values = ["GET"] }
  }
}

# Rule 4a: Game API GET reads (batch 1 — ALB max 5 path patterns per condition)
resource "aws_lb_listener_rule" "game_state_reads_1" {
  listener_arn = local.main_listener_arn
  priority     = 400

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.game_api.arn
  }

  condition {
    path_pattern {
      values = [
        "/game/*/state",
        "/game/*/spectator",
        "/game/*/waiting",
        "/game/*/escrow",
        "/game/*/funding",
      ]
    }
  }

  condition {
    http_request_method { values = ["GET"] }
  }
}

# Rule 4b: Game API GET reads (batch 2)
resource "aws_lb_listener_rule" "game_state_reads_2" {
  listener_arn = local.main_listener_arn
  priority     = 410

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.game_api.arn
  }

  condition {
    path_pattern {
      values = [
        "/game/*/settlement",
        "/game/*/offchain-settlement",
      ]
    }
  }

  condition {
    http_request_method { values = ["GET"] }
  }
}

# Rule 5: All POST /game/* → Game API (join, start, action, resign, chat, extend, streams)
resource "aws_lb_listener_rule" "game_writes" {
  listener_arn = local.main_listener_arn
  priority     = 500

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.game_api.arn
  }

  condition {
    path_pattern { values = ["/game/*"] }
  }

  condition {
    http_request_method { values = ["POST"] }
  }
}

# Rule 6: POST /stream/* → Game API (commentate)
resource "aws_lb_listener_rule" "stream_writes" {
  listener_arn = local.main_listener_arn
  priority     = 600

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.game_api.arn
  }

  condition {
    path_pattern { values = ["/stream/*"] }
  }

  condition {
    http_request_method { values = ["POST"] }
  }
}

# Rule 7: GET /stream/*/data → Game API (live stream data)
resource "aws_lb_listener_rule" "stream_data_reads" {
  listener_arn = local.main_listener_arn
  priority     = 610

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.game_api.arn
  }

  condition {
    path_pattern { values = ["/stream/*/data"] }
  }

  condition {
    http_request_method { values = ["GET"] }
  }
}

# Everything else (/, /leaderboard, /player/*, /api/games (GET), /api/leaderboard,
# /api/recent-hands, /api/stats/*, /api/streams, /api/config,
# /api/instructions, /game/*/streams (GET), static HTML) → Data API (default action)
