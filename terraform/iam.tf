# IAM for GitHub Actions (OIDC) and for SageMaker training/hosting execution roles.
# S3 ARNs reference bucket resources in s3.tf. SageMaker/Logs ARNs use the same name_prefix
# conventions as sagemaker.tf so policies apply without circular depends_on chains.
#
# Note: Workflows that run Terraform against many AWS services (creating IAM, state backends, etc.)
# usually need a broader role or human-driven apply than the ML-scoped GitHub policy below.

locals {
  # Names must stay aligned with resource "aws_sagemaker_*" blocks in sagemaker.tf.
  iam_sagemaker_model_name     = "log-anomaly-model"
  iam_sagemaker_ep_config_name = "log-anomaly-endpoint-config"
  iam_sagemaker_endpoint_name  = "log-anomaly-detector-endpoint"
  iam_sagemaker_pipeline_name  = "log-anomaly-detection-pipeline"
  # CloudWatch allows appending :* for all log streams under a named log group prefix (AWS IAM log ARN format).
  iam_sagemaker_ep_log_group_arn   = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/sagemaker/Endpoints/log-anomaly-detector-endpoint:*"
  iam_sagemaker_training_log_arn   = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/sagemaker/TrainingJobs:*"
  iam_sagemaker_processing_log_arn = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/sagemaker/ProcessingJobs:*"
  # One account-wide GitHub OIDC provider; Terraform may create it or adopt an existing one (see var.github_oidc_provider_use_existing).
  github_oidc_provider_arn = var.github_oidc_provider_use_existing ? data.aws_iam_openid_connect_provider.github_actions[0].arn : aws_iam_openid_connect_provider.github_actions[0].arn
}

# GitHub-provided OIDC issuer used by `aws-actions/configure-aws-credentials` and the `sub` claim.
data "aws_iam_openid_connect_provider" "github_actions" {
  count = var.github_oidc_provider_use_existing ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  count = var.github_oidc_provider_use_existing ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com",
  ]

  # GitHub publishes rotating intermediate CAs; keep both common thumbprints per AWS guidance.
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df6640f3",
  ]

  tags = merge(local.default_tags, {
    Name = "${local.name_prefix}-github-oidc"
  })
}

data "aws_iam_policy_document" "github_actions_assume" {
  statement {
    effect = "Allow"
    actions = [
      "sts:AssumeRoleWithWebIdentity",
    ]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Trust workflows in <github_org>/<github_repo> (e.g. YOUR_GITHUB_USERNAME/aws-log-anomaly-mlops).
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:${var.github_actions_ref_filter}"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${local.name_prefix}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume.json

  tags = merge(local.default_tags, {
    Name = "${local.name_prefix}-github-actions-role"
  })
}

# Pipeline / model / endpoint ARNs for CI (deploy, retrain, teardown). Pipeline name matches pipeline/definition.py default.
#
# CreatePipeline targets resource "*" until the pipeline exists; IAM denies CreatePipeline when the only
# allow is sagemaker:* on arn:...:pipeline/<name> — add a regional wildcard for pipeline lifecycle + runs.
data "aws_iam_policy_document" "github_actions_sagemaker" {
  statement {
    sid    = "SageMakerProjectResources"
    effect = "Allow"
    actions = [
      "sagemaker:*",
    ]
    resources = [
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:pipeline/${local.iam_sagemaker_pipeline_name}",
      aws_sagemaker_model.log_anomaly_model.arn,
      aws_sagemaker_endpoint_configuration.log_anomaly_endpoint_config.arn,
      aws_sagemaker_endpoint.log_anomaly_detector.arn,
    ]
  }
}

data "aws_iam_policy_document" "github_actions_sagemaker_pipelines_regional" {
  statement {
    sid    = "SageMakerPipelinesRegionalWildcard"
    effect = "Allow"
    actions = [
      "sagemaker:CreatePipeline",
      "sagemaker:UpdatePipeline",
      "sagemaker:DeletePipeline",
      "sagemaker:DescribePipeline",
      "sagemaker:ListPipelines",
      "sagemaker:StartPipelineExecution",
      "sagemaker:StopPipelineExecution",
      "sagemaker:DescribePipelineExecution",
      "sagemaker:ListPipelineExecutions",
      "sagemaker:ListPipelineExecutionSteps",
      "sagemaker:DescribePipelineDefinitionForExecution",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [data.aws_region.current.name]
    }
  }
}

data "aws_iam_policy_document" "github_actions_s3" {
  statement {
    sid    = "ProjectBucketsObjectCrud"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      "${aws_s3_bucket.raw_logs.arn}/*",
      "${aws_s3_bucket.processed_features.arn}/*",
      "${aws_s3_bucket.model_artifacts.arn}/*",
    ]
  }

  statement {
    sid    = "ProjectBucketsList"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [
      aws_s3_bucket.raw_logs.arn,
      aws_s3_bucket.processed_features.arn,
      aws_s3_bucket.model_artifacts.arn,
    ]
  }
}

data "aws_iam_policy_document" "github_actions_passrole" {
  statement {
    sid    = "PassSageMakerExecutionRoleOnly"
    effect = "Allow"
    actions = [
      "iam:PassRole",
    ]
    resources = [
      aws_iam_role.sagemaker_execution.arn,
    ]
  }
}

# ECR registry for Regional SageMaker image pulls (matches data.aws_sagemaker_prebuilt_ecr_image in sagemaker.tf).
# Approve/deploy job (ml-pipeline.yml): list/describe/approve packages; create ephemeral Model + EndpointConfig; update Endpoint.
data "aws_iam_policy_document" "github_actions_sagemaker_ml_deploy" {
  statement {
    sid    = "SageMakerModelPackagesRegistryRegional"
    effect = "Allow"
    actions = [
      "sagemaker:ListModelPackages",
      "sagemaker:DescribeModelPackage",
      "sagemaker:UpdateModelPackage",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [data.aws_region.current.name]
    }
  }

  statement {
    sid    = "SageMakerGithubDeployModelsConfigs"
    effect = "Allow"
    actions = [
      "sagemaker:CreateModel",
      "sagemaker:DescribeModel",
      "sagemaker:CreateEndpointConfig",
      "sagemaker:DescribeEndpointConfig",
    ]
    resources = [
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:model/log-anomaly-*",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:endpoint-config/log-anomaly-*",
    ]
  }
}

data "aws_iam_policy_document" "github_actions_ecr" {
  statement {
    sid    = "EcrAuthToken"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = [
      "*",
    ]
  }

  statement {
    sid    = "EcrPullScikitLearnImage"
    effect = "Allow"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [
      "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_sagemaker_prebuilt_ecr_image.sklearn_inference.registry_id}:repository/sagemaker-scikit-learn",
    ]
  }
}

data "aws_iam_policy_document" "github_actions_combined" {
  source_policy_documents = [
    data.aws_iam_policy_document.github_actions_sagemaker.json,
    data.aws_iam_policy_document.github_actions_sagemaker_pipelines_regional.json,
    data.aws_iam_policy_document.github_actions_sagemaker_ml_deploy.json,
    data.aws_iam_policy_document.github_actions_s3.json,
    data.aws_iam_policy_document.github_actions_passrole.json,
    data.aws_iam_policy_document.github_actions_ecr.json,
  ]
}

resource "aws_iam_role_policy" "github_actions" {
  name   = "${local.name_prefix}-github-actions-inline"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_combined.json
}

data "aws_iam_policy_document" "sagemaker_assume" {
  statement {
    effect = "Allow"
    actions = [
      "sts:AssumeRole",
    ]

    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sagemaker_execution" {
  name               = "${local.name_prefix}-sagemaker-exec"
  assume_role_policy = data.aws_iam_policy_document.sagemaker_assume.json

  tags = merge(local.default_tags, {
    Name = "${local.name_prefix}-sagemaker-execution"
  })
}

# Scoped S3 object + list permissions on project buckets only (no account-wide bucket access).
data "aws_iam_policy_document" "sagemaker_execution_s3" {
  statement {
    sid    = "ProjectBucketsFullForJobs"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
      "s3:ListBucketMultipartUploads",
    ]
    resources = [
      "${aws_s3_bucket.raw_logs.arn}/*",
      "${aws_s3_bucket.processed_features.arn}/*",
      "${aws_s3_bucket.model_artifacts.arn}/*",
    ]
  }

  statement {
    sid    = "ProjectBucketsList"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:ListBucketVersions",
    ]
    resources = [
      aws_s3_bucket.raw_logs.arn,
      aws_s3_bucket.processed_features.arn,
      aws_s3_bucket.model_artifacts.arn,
    ]
  }
}

data "aws_iam_policy_document" "sagemaker_execution_logs" {
  statement {
    sid    = "CloudWatchLogsForSageMakerJobs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
      "logs:DescribeLogGroups",
    ]
    resources = [
      local.iam_sagemaker_training_log_arn,
      local.iam_sagemaker_processing_log_arn,
      local.iam_sagemaker_ep_log_group_arn,
    ]
  }
}

data "aws_iam_policy_document" "sagemaker_execution_ecr" {
  statement {
    sid    = "EcrAuthToken"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = [
      "*",
    ]
  }

  statement {
    sid    = "EcrPullScikitLearnImage"
    effect = "Allow"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [
      "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_sagemaker_prebuilt_ecr_image.sklearn_inference.registry_id}:repository/sagemaker-scikit-learn",
    ]
  }
}

# SageMaker Pipelines runs steps under credentials derived from PipelineRoleArn / execution identity;
# launching ProcessingJob / TrainingJob requires iam:PassRole on the RoleArn passed into those APIs
# (here: the same execution role). Without this, CreateProcessingJob fails with PassRole denied.
data "aws_iam_policy_document" "sagemaker_execution_passrole_self" {
  statement {
    sid    = "PassExecutionRoleToSageMakerJobs"
    effect = "Allow"
    actions = [
      "iam:PassRole",
    ]
    resources = [
      aws_iam_role.sagemaker_execution.arn,
    ]
  }
}

# SageMaker control plane operations for jobs and hosted resources scoped to this project’s naming prefix and ARNs.
# Pipeline steps name jobs with a "pipelines-{id}-{StepName}-{suffix}" pattern, not ${name_prefix}-*;
# include those ARNs so CreateProcessingJob / AddTags / training jobs resolve (sagemaker:AddTags on job ARNs).
#
# RegisterModel (ModelBuilding Pipelines): CreateModelPackageGroup / CreateModelPackage + AddTags targets
# model-package-group/<name>; those ARNs must be allowed here alongside pipeline/*.
data "aws_iam_policy_document" "sagemaker_execution_service" {
  statement {
    sid    = "SageMakerOperationsOnProjectResources"
    effect = "Allow"
    actions = [
      "sagemaker:*",
    ]
    resources = [
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:pipeline/${local.iam_sagemaker_pipeline_name}",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:model/${local.iam_sagemaker_model_name}",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:endpoint-config/${local.iam_sagemaker_ep_config_name}",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:endpoint/${local.iam_sagemaker_endpoint_name}",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:training-job/${local.name_prefix}-*",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:processing-job/${local.name_prefix}-*",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:transform-job/${local.name_prefix}-*",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:training-job/pipelines-*",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:processing-job/pipelines-*",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:transform-job/pipelines-*",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:model-package-group/*",
      "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:model-package/*",
    ]
  }
}

data "aws_iam_policy_document" "sagemaker_execution_combined" {
  source_policy_documents = [
    data.aws_iam_policy_document.sagemaker_execution_s3.json,
    data.aws_iam_policy_document.sagemaker_execution_logs.json,
    data.aws_iam_policy_document.sagemaker_execution_ecr.json,
    data.aws_iam_policy_document.sagemaker_execution_passrole_self.json,
    data.aws_iam_policy_document.sagemaker_execution_service.json,
  ]
}

resource "aws_iam_role_policy" "sagemaker_execution" {
  name   = "${local.name_prefix}-sagemaker-exec-inline"
  role   = aws_iam_role.sagemaker_execution.id
  policy = data.aws_iam_policy_document.sagemaker_execution_combined.json
}
