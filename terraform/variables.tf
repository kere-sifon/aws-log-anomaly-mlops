variable "aws_region" {
  type        = string
  description = "AWS region for all regional resources (default aligns with Canada deployment)."
  default     = "ca-central-1"
}

variable "project_name" {
  type        = string
  description = "Short project label used in resource names and tagging (e.g. aws-log-anomaly-mlops)."
  default     = "aws-log-anomaly-mlops"
}

variable "environment" {
  type        = string
  description = "Deployment stage (e.g. dev, staging, prod) for tagging and naming."
  default     = "dev"
}

variable "github_org" {
  type        = string
  description = "GitHub organization or user that owns the repository used for OIDC trust."
  default     = "YOUR_GITHUB_ORG"
}

variable "github_repo" {
  type        = string
  description = "GitHub repository name (without org) allowed to assume the GitHub Actions IAM role."
  default     = "aws-log-anomaly-mlops"
}

variable "github_actions_ref_filter" {
  type        = string
  description = "Optional ref pattern for OIDC subject claim (e.g. ref:refs/heads/main or * for any branch)."
  default     = "*"
}

variable "github_oidc_provider_use_existing" {
  type        = bool
  description = "If true, use the account's existing GitHub Actions OIDC provider (https://token.actions.githubusercontent.com) instead of creating it. Default true because many accounts already register this URL once; set false only for a brand-new account with no GitHub OIDC provider yet."
  default     = true
}

variable "sagemaker_endpoint_instance_type" {
  type        = string
  description = "Instance type for real-time inference (informational; `terraform/sagemaker.tf` fixes the endpoint config to ml.t2.medium per project defaults)."
  default     = "ml.t2.medium"
}

variable "sklearn_inference_image_tag" {
  type        = string
  description = "Tag for the regional SageMaker Scikit-learn inference image (see AWS ECR paths for your region)."
  default     = "1.2-1-cpu-py3"
}

variable "model_data_s3_object_key" {
  type        = string
  description = "S3 key under the model artifacts bucket pointing to a packaged model.tar.gz (placeholder until first training)."
  default     = "models/placeholder/model.tar.gz"
}
