# AWS provider and shared data sources for the log anomaly MLOps stack.

locals {
  # Applied via provider default_tags and repeated in resources that require explicit tags blocks.
  default_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  name_prefix = "${var.project_name}-${var.environment}"
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.default_tags
  }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
