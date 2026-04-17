output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions after AWS OIDC federation (set as deployment role in workflows)."
  value       = aws_iam_role.github_actions.arn
}

output "sagemaker_execution_role_arn" {
  description = "IAM role passed to SageMaker for training, processing, and inference."
  value       = aws_iam_role.sagemaker_execution.arn
}

output "s3_raw_logs_bucket_name" {
  description = "Name of the raw log landing zone bucket."
  value       = aws_s3_bucket.raw_logs.bucket
}

output "s3_raw_logs_bucket_arn" {
  description = "ARN of the raw log landing zone bucket."
  value       = aws_s3_bucket.raw_logs.arn
}

output "s3_processed_features_bucket_name" {
  description = "Name of the engineered features bucket."
  value       = aws_s3_bucket.processed_features.bucket
}

output "s3_processed_features_bucket_arn" {
  description = "ARN of the engineered features bucket."
  value       = aws_s3_bucket.processed_features.arn
}

output "s3_model_artifacts_bucket_name" {
  description = "Name of the SageMaker model artifact bucket."
  value       = aws_s3_bucket.model_artifacts.bucket
}

output "s3_model_artifacts_bucket_arn" {
  description = "ARN of the SageMaker model artifact bucket."
  value       = aws_s3_bucket.model_artifacts.arn
}

output "sagemaker_endpoint_name" {
  description = "Real-time SageMaker endpoint name for inference invocations."
  value       = aws_sagemaker_endpoint.log_anomaly_detector.name
}

output "sagemaker_endpoint_arn" {
  description = "ARN of the SageMaker hosted endpoint."
  value       = aws_sagemaker_endpoint.log_anomaly_detector.arn
}

output "sagemaker_endpoint_config_name" {
  description = "SageMaker endpoint configuration backing the hosted endpoint."
  value       = aws_sagemaker_endpoint_configuration.log_anomaly_endpoint_config.name
}

output "sns_log_anomaly_alerts_topic_arn" {
  description = "SNS topic ARN for SageMaker / pipeline alerts."
  value       = aws_sns_topic.log_anomaly_alerts.arn
}
