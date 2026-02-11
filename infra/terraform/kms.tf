# ---------- KMS key for Nitro Enclave attestation ----------
#
# The key policy allows kms:Decrypt ONLY when the request includes
# an attestation document whose PCR-0 matches the expected enclave image.
# This ensures the SERVER_PRIVATE_KEY can only be decrypted inside the
# exact enclave binary we built and published.
#
# Conditional on var.enclave_enabled — when false, none of this is created.

resource "aws_kms_key" "enclave" {
  count = var.enclave_enabled ? 1 : 0

  description             = "Monteclaude enclave attestation key (${var.environment})"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Allow account root full key management (required for Terraform to manage it)
      {
        Sid    = "AllowRootAccountFullAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      # Allow encrypt from the Game API role (for initial key encryption)
      {
        Sid    = "AllowEncrypt"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.game_api.arn
        }
        Action   = ["kms:Encrypt", "kms:GenerateDataKey"]
        Resource = "*"
      },
      # Allow decrypt ONLY with valid attestation matching PCR-0
      {
        Sid    = "AllowDecryptWithAttestation"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.game_api.arn
        }
        Action   = "kms:Decrypt"
        Resource = "*"
        Condition = {
          StringEqualsIgnoreCase = {
            "kms:RecipientAttestation:ImageSha384" = var.enclave_pcr0
          }
        }
      }
    ]
  })

  tags = { Name = "monteclaude-enclave-${var.environment}" }
}

data "aws_caller_identity" "current" {}

resource "aws_kms_alias" "enclave" {
  count = var.enclave_enabled ? 1 : 0

  name          = "alias/monteclaude-enclave-${var.environment}"
  target_key_id = aws_kms_key.enclave[0].key_id
}
