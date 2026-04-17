# Default variable assignments (see variables.tf). Terraform auto-loads this file.
# Override locally with another file via -var-file=... if you need secrets or one-off values.

aws_region                       = "ca-central-1"
project_name                     = "aws-log-anomaly-mlops"
environment                      = "dev"
github_org                       = "kere-sifon"
github_repo                      = "aws-log-anomaly-mlops"
github_actions_ref_filter        = "*"
sagemaker_endpoint_instance_type = "ml.t2.medium"
sklearn_inference_image_tag      = "1.2-1-cpu-py3"
model_data_s3_object_key         = "models/placeholder/model.tar.gz"
