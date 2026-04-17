# SageMaker model, endpoint configuration, and real-time endpoint for scikit-learn Isolation Forest inference.
# Container URI comes from the regional sklearn image (default region: ca-central-1).

data "aws_sagemaker_prebuilt_ecr_image" "sklearn_inference" {
  repository_name = "sagemaker-scikit-learn"
  image_tag      = var.sklearn_inference_image_tag
}

resource "aws_sagemaker_model" "log_anomaly_model" {
  name              = "log-anomaly-model"
  execution_role_arn = aws_iam_role.sagemaker_execution.arn

  primary_container {
    image          = data.aws_sagemaker_prebuilt_ecr_image.sklearn_inference.registry_path
    mode           = "SingleModel"
    model_data_url = "s3://${aws_s3_bucket.model_artifacts.bucket}/${aws_s3_object.bootstrap_model_artifact.key}"
    environment    = {
      # Module name for code/inference.py (no .py suffix; importlib.import_module).
      SAGEMAKER_PROGRAM = "inference"
    }
  }

  depends_on = [aws_s3_object.bootstrap_model_artifact]

  tags = local.default_tags
}

resource "aws_sagemaker_endpoint_configuration" "log_anomaly_endpoint_config" {
  name = "log-anomaly-endpoint-config"

  depends_on = [aws_sagemaker_model.log_anomaly_model]

  production_variants {
    variant_name                                     = "primary"
    model_name                                       = aws_sagemaker_model.log_anomaly_model.name
    initial_instance_count                           = 1
    instance_type                                    = "ml.t2.medium"
    initial_variant_weight                           = 1
    # Defaults are short; first-time image pull + model load can exceed them and surface as ping failures.
    model_data_download_timeout_in_seconds           = 900
    container_startup_health_check_timeout_in_seconds = 900
  }

  tags = local.default_tags
}

resource "aws_sagemaker_endpoint" "log_anomaly_detector" {
  name                = "log-anomaly-detector-endpoint"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.log_anomaly_endpoint_config.name
  tags                = local.default_tags

  depends_on = [
    aws_sagemaker_model.log_anomaly_model,
    aws_sagemaker_endpoint_configuration.log_anomaly_endpoint_config,
  ]

  lifecycle {
    ignore_changes = [
      endpoint_config_name,
    ]
  }
}
