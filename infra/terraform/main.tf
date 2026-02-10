terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  backend "s3" {
    bucket         = "monteclaude-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "monteclaude-terraform-locks"
    encrypt        = true
    profile        = "monte"
  }
}

provider "aws" {
  region  = var.aws_region
  profile = "monte"

  default_tags {
    tags = {
      Project     = "monteclaude"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
