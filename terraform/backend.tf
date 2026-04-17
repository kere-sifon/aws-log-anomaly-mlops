# Remote state on HCP Terraform (Terraform Cloud at app.terraform.io).
# Replace YOUR_ORG and workspace name with your Terraform Cloud organization and workspace.
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  cloud {
    organization = "kere-terra"

    workspaces {
      name = "aws-log-anomaly-mlops"
    }
  }
}
