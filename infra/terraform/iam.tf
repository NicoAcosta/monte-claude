# ---------- ECR repositories ----------

resource "aws_ecr_repository" "game_api" {
  name                 = "monteclaude/game-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "data_api" {
  name                 = "monteclaude/data-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Lifecycle: keep last 10 images, expire untagged after 7 days
locals {
  ecr_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep last 10 tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPatternList = ["*"]
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

resource "aws_ecr_lifecycle_policy" "game_api" {
  repository = aws_ecr_repository.game_api.name
  policy     = local.ecr_lifecycle_policy
}

resource "aws_ecr_lifecycle_policy" "data_api" {
  repository = aws_ecr_repository.data_api.name
  policy     = local.ecr_lifecycle_policy
}

# ---------- IAM role for Game API EC2 ----------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "game_api" {
  name               = "monteclaude-game-api-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role" "data_api" {
  name               = "monteclaude-data-api-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# SSM for both (remote management without SSH)
resource "aws_iam_role_policy_attachment" "game_api_ssm" {
  role       = aws_iam_role.game_api.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "data_api_ssm" {
  role       = aws_iam_role.data_api.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# CloudWatch logs
resource "aws_iam_role_policy_attachment" "game_api_cw" {
  role       = aws_iam_role.game_api.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_role_policy_attachment" "data_api_cw" {
  role       = aws_iam_role.data_api.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# ECR pull for both
data "aws_iam_policy_document" "ecr_pull" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = [
      aws_ecr_repository.game_api.arn,
      aws_ecr_repository.data_api.arn,
    ]
  }
}

resource "aws_iam_role_policy" "game_api_ecr" {
  name   = "ecr-pull"
  role   = aws_iam_role.game_api.id
  policy = data.aws_iam_policy_document.ecr_pull.json
}

resource "aws_iam_role_policy" "data_api_ecr" {
  name   = "ecr-pull"
  role   = aws_iam_role.data_api.id
  policy = data.aws_iam_policy_document.ecr_pull.json
}

# Secrets Manager — Game API gets all secrets
data "aws_iam_policy_document" "game_api_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.db_credentials.arn,
      aws_secretsmanager_secret.server_private_key.arn,
      aws_secretsmanager_secret.rpc_url.arn,
      aws_secretsmanager_secret.factory_address.arn,
    ]
  }
}

resource "aws_iam_role_policy" "game_api_secrets" {
  name   = "secrets-read"
  role   = aws_iam_role.game_api.id
  policy = data.aws_iam_policy_document.game_api_secrets.json
}

# Secrets Manager — Data API gets DB credentials only
data "aws_iam_policy_document" "data_api_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db_credentials.arn]
  }
}

resource "aws_iam_role_policy" "data_api_secrets" {
  name   = "secrets-read"
  role   = aws_iam_role.data_api.id
  policy = data.aws_iam_policy_document.data_api_secrets.json
}

# Instance profiles
resource "aws_iam_instance_profile" "game_api" {
  name = "monteclaude-game-api-${var.environment}"
  role = aws_iam_role.game_api.name
}

resource "aws_iam_instance_profile" "data_api" {
  name = "monteclaude-data-api-${var.environment}"
  role = aws_iam_role.data_api.name
}
