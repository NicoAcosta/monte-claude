# ---------- ECR repositories ----------

resource "aws_ecr_repository" "game_api" {
  name                 = "monteclaude/game-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "data_api" {
  name                 = "monteclaude/data-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "account_api" {
  name                 = "monteclaude/account-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "monteclaude/frontend"
  image_tag_mutability = "IMMUTABLE"
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
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = 10
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

resource "aws_ecr_lifecycle_policy" "account_api" {
  repository = aws_ecr_repository.account_api.name
  policy     = local.ecr_lifecycle_policy
}

resource "aws_ecr_lifecycle_policy" "frontend" {
  repository = aws_ecr_repository.frontend.name
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

# ECR pull — Game API role (only needs game-api repo)
data "aws_iam_policy_document" "game_api_ecr_pull" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = [aws_ecr_repository.game_api.arn]
  }
}

resource "aws_iam_role_policy" "game_api_ecr" {
  name   = "ecr-pull"
  role   = aws_iam_role.game_api.id
  policy = data.aws_iam_policy_document.game_api_ecr_pull.json
}

# ECR pull — Data API role (needs data-api + account-api repos, since Account API is co-located)
data "aws_iam_policy_document" "data_api_ecr_pull" {
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
      aws_ecr_repository.data_api.arn,
      aws_ecr_repository.account_api.arn,
      aws_ecr_repository.frontend.arn,
    ]
  }
}

resource "aws_iam_role_policy" "data_api_ecr" {
  name   = "ecr-pull"
  role   = aws_iam_role.data_api.id
  policy = data.aws_iam_policy_document.data_api_ecr_pull.json
}

# Secrets Manager — Game API gets all secrets
data "aws_iam_policy_document" "game_api_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = concat(
      [
        aws_secretsmanager_secret.db_credentials.arn,
        aws_secretsmanager_secret.server_private_key.arn,
        aws_secretsmanager_secret.rpc_url.arn,
        aws_secretsmanager_secret.factory_address.arn,
      ],
      var.enclave_enabled ? [aws_secretsmanager_secret.server_private_key_encrypted[0].arn] : [],
    )
  }
}

resource "aws_iam_role_policy" "game_api_secrets" {
  name   = "secrets-read"
  role   = aws_iam_role.game_api.id
  policy = data.aws_iam_policy_document.game_api_secrets.json
}

# KMS — Game API can encrypt (for initial key setup) and decrypt (via enclave attestation)
data "aws_iam_policy_document" "game_api_kms" {
  count = var.enclave_enabled ? 1 : 0

  statement {
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.enclave[0].arn]
  }
}

resource "aws_iam_role_policy" "game_api_kms" {
  count = var.enclave_enabled ? 1 : 0

  name   = "kms-enclave"
  role   = aws_iam_role.game_api.id
  policy = data.aws_iam_policy_document.game_api_kms[0].json
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

# ---------- GitHub OIDC for CI/CD ----------

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_deploy_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:bauti-defi/monte-claude:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "monteclaude-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_deploy_assume.json
}

data "aws_iam_policy_document" "github_deploy_permissions" {
  # ECR push to all repos
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:BatchCheckLayerAvailability",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = [
      aws_ecr_repository.game_api.arn,
      aws_ecr_repository.data_api.arn,
      aws_ecr_repository.account_api.arn,
      aws_ecr_repository.frontend.arn,
    ]
  }
  # SSM SendCommand — scoped to our EC2 instances only
  statement {
    actions = ["ssm:SendCommand"]
    resources = [
      aws_instance.game_api.arn,
      aws_instance.data_api.arn,
      "arn:aws:ssm:${var.aws_region}::document/AWS-RunShellScript",
    ]
  }
  statement {
    actions   = ["ssm:GetCommandInvocation"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "deploy-permissions"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy_permissions.json
}
