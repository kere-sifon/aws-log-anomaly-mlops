# IAM roles

This repo defines two application IAM roles in [`terraform/iam.tf`](../terraform/iam.tf). **Authoritative grants** are Terraform **`data.aws_iam_policy_document`** blocks merged into inline role policies. The JSON below is a **human-readable summary** with placeholders; **apply Terraform** to materialize real ARNs in AWS.

| Placeholder | Meaning |
| --- | --- |
| `{region}` | AWS region (e.g. `ca-central-1`) |
| `{account_id}` | 12-digit account ID |
| `{name_prefix}` | `local.name_prefix` from Terraform (e.g. `project-environment`) |
| `{github_org}`, `{github_repo}` | From `terraform/terraform.tfvars` |
| `{github_actions_ref_filter}` | From `var.github_actions_ref_filter` (e.g. `ref:refs/heads/main` or `*`) |
| `{sklearn_ecr_registry_id}` | SageMaker prebuilt ECR account for the region (see `data.aws_sagemaker_prebuilt_ecr_image` in `terraform/sagemaker.tf`) |

---

## 1. GitHub Actions — ML pipeline / deploy

| | |
| --- | --- |
| **Terraform** | `aws_iam_role.github_actions` |
| **Name** | `{name_prefix}-github-actions` |
| **Output** | `github_actions_role_arn` |
| **Used as** | `AWS_ML_PIPELINE_ROLE_ARN` in `.github/workflows/ml-pipeline.yml` |

### Trust policy

GitHub OIDC (`aws-actions/configure-aws-credentials`). The OIDC provider ARN may be created or looked up by Terraform (`github_oidc_provider_use_existing`).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::{account_id}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:{github_org}/{github_repo}:{github_actions_ref_filter}"
        }
      }
    }
  ]
}
```

### Permissions (inline policy)

Equivalent to merging: `github_actions_sagemaker`, `github_actions_sagemaker_pipelines_regional`, `github_actions_sagemaker_ml_deploy`, `github_actions_s3`, `github_actions_passrole`, `github_actions_ecr`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SageMakerProjectResources",
      "Effect": "Allow",
      "Action": "sagemaker:*",
      "Resource": [
        "arn:aws:sagemaker:{region}:{account_id}:pipeline/log-anomaly-detection-pipeline",
        "arn:aws:sagemaker:{region}:{account_id}:model/log-anomaly-model",
        "arn:aws:sagemaker:{region}:{account_id}:endpoint-config/log-anomaly-endpoint-config",
        "arn:aws:sagemaker:{region}:{account_id}:endpoint/log-anomaly-detector-endpoint"
      ]
    },
    {
      "Sid": "SageMakerPipelinesRegionalWildcard",
      "Effect": "Allow",
      "Action": [
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
        "sagemaker:DescribePipelineDefinitionForExecution"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "{region}"
        }
      }
    },
    {
      "Sid": "SageMakerModelPackagesRegistryRegional",
      "Effect": "Allow",
      "Action": [
        "sagemaker:ListModelPackages",
        "sagemaker:DescribeModelPackage",
        "sagemaker:UpdateModelPackage"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "{region}"
        }
      }
    },
    {
      "Sid": "SageMakerGithubDeployModelsConfigs",
      "Effect": "Allow",
      "Action": [
        "sagemaker:CreateModel",
        "sagemaker:DescribeModel",
        "sagemaker:CreateEndpointConfig",
        "sagemaker:DescribeEndpointConfig"
      ],
      "Resource": [
        "arn:aws:sagemaker:{region}:{account_id}:model/log-anomaly-*",
        "arn:aws:sagemaker:{region}:{account_id}:endpoint-config/log-anomaly-*"
      ]
    },
    {
      "Sid": "SageMakerGithubDeployUpdateEndpoint",
      "Effect": "Allow",
      "Action": [
        "sagemaker:DescribeEndpoint",
        "sagemaker:UpdateEndpoint"
      ],
      "Resource": [
        "arn:aws:sagemaker:{region}:{account_id}:endpoint/log-anomaly-detector-endpoint",
        "arn:aws:sagemaker:{region}:{account_id}:endpoint-config/log-anomaly-*"
      ]
    },
    {
      "Sid": "ProjectBucketsObjectCrud",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::{raw_logs_bucket}/*",
        "arn:aws:s3:::{processed_features_bucket}/*",
        "arn:aws:s3:::{model_artifacts_bucket}/*"
      ]
    },
    {
      "Sid": "ProjectBucketsList",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::{raw_logs_bucket}",
        "arn:aws:s3:::{processed_features_bucket}",
        "arn:aws:s3:::{model_artifacts_bucket}"
      ]
    },
    {
      "Sid": "PassSageMakerExecutionRoleOnly",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::{account_id}:role/{name_prefix}-sagemaker-exec"
    },
    {
      "Sid": "EcrAuthToken",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "EcrPullScikitLearnImage",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "arn:aws:ecr:{region}:{sklearn_ecr_registry_id}:repository/sagemaker-scikit-learn"
    }
  ]
}
```

Project S3 bucket names follow Terraform resources in `terraform/s3.tf`; substitute from **`terraform output`** or console. The **PassRole** target is `aws_iam_role.sagemaker_execution`.

---

## 2. SageMaker execution

| | |
| --- | --- |
| **Terraform** | `aws_iam_role.sagemaker_execution` |
| **Name** | `{name_prefix}-sagemaker-exec` |
| **Output** | `sagemaker_execution_role_arn` |
| **Used as** | `SAGEMAKER_EXECUTION_ROLE_ARN` (pipeline **`RoleArn`**, training, processing, **CreateModel**) |

### Trust policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "sagemaker.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### Permissions (inline policy)

Equivalent to merging: `sagemaker_execution_s3`, `sagemaker_execution_logs`, `sagemaker_execution_ecr`, `sagemaker_execution_passrole_self`, `sagemaker_execution_service`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ProjectBucketsFullForJobs",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts",
        "s3:ListBucketMultipartUploads"
      ],
      "Resource": [
        "arn:aws:s3:::{raw_logs_bucket}/*",
        "arn:aws:s3:::{processed_features_bucket}/*",
        "arn:aws:s3:::{model_artifacts_bucket}/*"
      ]
    },
    {
      "Sid": "ProjectBucketsList",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "s3:ListBucketVersions"
      ],
      "Resource": [
        "arn:aws:s3:::{raw_logs_bucket}",
        "arn:aws:s3:::{processed_features_bucket}",
        "arn:aws:s3:::{model_artifacts_bucket}"
      ]
    },
    {
      "Sid": "CloudWatchLogsForSageMakerJobs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams",
        "logs:DescribeLogGroups"
      ],
      "Resource": [
        "arn:aws:logs:{region}:{account_id}:log-group:/aws/sagemaker/TrainingJobs:*",
        "arn:aws:logs:{region}:{account_id}:log-group:/aws/sagemaker/ProcessingJobs:*",
        "arn:aws:logs:{region}:{account_id}:log-group:/aws/sagemaker/Endpoints/log-anomaly-detector-endpoint:*"
      ]
    },
    {
      "Sid": "EcrAuthToken",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "EcrPullScikitLearnImage",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "arn:aws:ecr:{region}:{sklearn_ecr_registry_id}:repository/sagemaker-scikit-learn"
    },
    {
      "Sid": "PassExecutionRoleToSageMakerJobs",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::{account_id}:role/{name_prefix}-sagemaker-exec"
    },
    {
      "Sid": "SageMakerOperationsOnProjectResources",
      "Effect": "Allow",
      "Action": "sagemaker:*",
      "Resource": [
        "arn:aws:sagemaker:{region}:{account_id}:pipeline/log-anomaly-detection-pipeline",
        "arn:aws:sagemaker:{region}:{account_id}:model/log-anomaly-model",
        "arn:aws:sagemaker:{region}:{account_id}:endpoint-config/log-anomaly-endpoint-config",
        "arn:aws:sagemaker:{region}:{account_id}:endpoint/log-anomaly-detector-endpoint",
        "arn:aws:sagemaker:{region}:{account_id}:training-job/{name_prefix}-*",
        "arn:aws:sagemaker:{region}:{account_id}:processing-job/{name_prefix}-*",
        "arn:aws:sagemaker:{region}:{account_id}:transform-job/{name_prefix}-*",
        "arn:aws:sagemaker:{region}:{account_id}:training-job/pipelines-*",
        "arn:aws:sagemaker:{region}:{account_id}:processing-job/pipelines-*",
        "arn:aws:sagemaker:{region}:{account_id}:transform-job/pipelines-*",
        "arn:aws:sagemaker:{region}:{account_id}:model-package-group/*",
        "arn:aws:sagemaker:{region}:{account_id}:model-package/*"
      ]
    }
  ]
}
```

---

## 3. Terraform bootstrap (not defined in `terraform/iam.tf`)

**`AWS_TF_ROLE_ARN`** (e.g. **`infra.yml`**) is a **separate** role you maintain: it must be able to **apply** this module (create OIDC provider, S3, SNS, IAM roles above, SageMaker, etc.). It is **not** the GitHub ML role. See [README.md](../README.md) section **IAM for Terraform CI**.

---

## Drift and review

- After changing [`terraform/iam.tf`](../terraform/iam.tf), update this file if statement SIDs or actions change.
- To export **live** policies from AWS: **IAM → Roles → &lt;role&gt; → Permissions → JSON** (post-apply).
