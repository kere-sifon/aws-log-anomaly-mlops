# aws-log-anomaly-mlops

Terraform + SageMaker (Python SDK) + GitHub Actions scaffold for training and hosting an **Isolation Forest** model that flags anomalous engineered log-feature vectors.

## Layout

| Path | Purpose |
| --- | --- |
| `terraform/` | AWS resources: S3 buckets, OIDC IAM for GitHub Actions, SageMaker roles/model/endpoint (ml.t2.medium), CloudWatch alarms |
| `pipeline/` | SageMaker Pipeline definition (`build_pipeline()` runs `training/train.py` on **ml.m5.xlarge** with **managed spot**) |
| `training/` | SageMaker training entrypoint (`IsolationForest`) |
| `inference/` | Realtime inference handlers compatible with the SageMaker scikit-learn image |
| `.github/workflows/` | CI for Terraform (HCP Terraform backend) and the ML pipeline |

## Prerequisites

- Terraform **>= 1.5** and the **Terraform Cloud** (HCP Terraform) organization/workspace referenced in `terraform/backend.tf`.
- AWS account + CLI profile (for local testing) with rights mirroring the GitHub Actions role.
- GitHub repository settings that allow **OpenID Connect** to AWS (no long-lived access keys in CI).

## Configure Terraform

1. In `terraform/backend.tf`, replace `YOUR_TERRAFORM_CLOUD_ORG` with your Terraform Cloud organization and adjust the `workspaces` `name` if needed.
2. Edit `terraform/terraform.tfvars` (tracked in git with defaults) for shared settings such as `github_org`, `github_repo`, `environment`, or region. Terraform loads it automatically in the `terraform/` directory, including in GitHub Actions. For sensitive or personal overrides, keep a separate file (e.g. `terraform/secrets.tfvars`, gitignored) and run with `-var-file=secrets.tfvars`.
3. Set `TF_TOKEN_app_terraform_io` (or `TF_TOKEN`) locally when running Terraform against the remote backend.

## GitHub Actions secrets (documented)

| Secret | Used by | Purpose |
| --- | --- | --- |
| `TF_API_TOKEN` | `infra.yml` | Terraform Cloud (HCP Terraform) API token for the `cloud` backend |
| `AWS_TF_ROLE_ARN` | `infra.yml`, `ml-pipeline.yml` | IAM role **ARN** GitHub Actions assumes via OIDC. Must be able to **create** this stack (IAM OIDC provider, roles, S3, SNS, CloudWatch, SageMaker). See **IAM for Terraform CI** below. |

The ML workflow also needs repository variable **`SAGEMAKER_EXECUTION_ROLE_ARN`** (the role **SageMaker** assumes); set it from `terraform output -raw sagemaker_execution_role_arn` after apply.

### IAM for Terraform CI (`AWS_TF_ROLE_ARN`)

Terraform in this repo **creates** AWS resources including **`iam:CreateOpenIDConnectProvider`**, **`s3:CreateBucket`**, **`sns:CreateTopic`**, **`logs:CreateLogGroup`**, and SageMaker resources. The IAM role referenced by **`AWS_TF_ROLE_ARN`** must allow those actions.

The role Terraform **defines** in `terraform/iam.tf` (`github_actions`, output `github_actions_role_arn`) is **scoped** to SageMaker/S3 for day‑to‑day pipeline use and **does not** grant IAM or bucket **creation** for the Terraform runner. **Do not** set `AWS_TF_ROLE_ARN` to that output for the **infra** workflow — apply would fail whenever IAM or new buckets must be created or changed.

Use a **dedicated CI / bootstrap role** trusted by GitHub OIDC (the role you name `GithubActions` or similar) and attach a policy that allows Terraform to manage this stack. Prefer a **scoped** JSON policy (explicit actions and ARNs for this module); you can keep it under **`terraform/policies/`** locally — that directory is **gitignored** so account-specific ARNs are not committed. For a sandbox only, **AdministratorAccess** is an alternative. In IAM: **Policies → Create policy → JSON**, paste your policy, then attach it to the role assumed by `AWS_TF_ROLE_ARN`.

Configure a **GitHub Environment** named `production` with required reviewers if you use the gated `terraform-apply` job in `infra.yml`.

You can also run **Actions → Terraform (AWS OIDC + HCP Terraform) → Run workflow** and choose **plan**, **apply**, or **destroy**. Apply and destroy use the `production` environment. **Destroy** with an empty **destroy targets** field removes everything in the current Terraform state (full teardown of what this config manages). Optionally set **destroy targets** (one resource address per line) for a partial destroy only.

If you name roles differently, update the workflows to match.

### Repository variables (GitHub **Settings → Secrets and variables → Actions → Variables**)

| Variable | Used by | Purpose |
| --- | --- | --- |
| `AWS_REGION` | `infra.yml`, `ml-pipeline.yml` | AWS region (workflows default to `ca-central-1` if unset) |
| `TERRAFORM_VERSION` | `infra.yml` | Optional; Terraform CLI version for `setup-terraform` (default `1.5.7`) |
| `MODEL_PACKAGE_GROUP_NAME` | `ml-pipeline.yml` | Model package group (e.g. `LogAnomalyDetectors`); must match `pipeline/definition.py` |
| `SAGEMAKER_PIPELINE_NAME` | `ml-pipeline.yml` | SageMaker Pipeline name (defaults to `log-anomaly-detection-pipeline` if unset) |
| `SAGEMAKER_ENDPOINT_NAME` | `ml-pipeline.yml` | Live endpoint to update after approval (e.g. Terraform output) |
| `SAGEMAKER_EXECUTION_ROLE_ARN` | `ml-pipeline.yml` | SageMaker execution role ARN (`sagemaker_execution` in Terraform): pipeline `upsert`, training, and `CreateModel` |
| `SAGEMAKER_INFERENCE_INSTANCE_TYPE` | `ml-pipeline.yml` | Optional; defaults to `ml.t2.medium` |

## Local quick checks

```bash
cd terraform && terraform fmt -recursive && terraform validate
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -c "from pipeline.definition import build_pipeline; build_pipeline()"
python training/train.py  # writes to SM paths if unset; uses synthetic data
```

## SageMaker training vs endpoint

- **Training** (SDK / pipeline): **ml.m5.xlarge**, **spot** enabled in `pipeline/definition.py` and reflected in comments.
- **Hosting** (Terraform `aws_sagemaker_endpoint`): **ml.t2.medium** on the endpoint configuration.


## License

Provided as sample infrastructure and application code; apply your organization’s policies before production use.
