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
2. Optional: create `terraform/terraform.tfvars` (gitignored) to override `github_org` / `github_repo` and other variables.
3. Set `TF_TOKEN_app_terraform_io` (or `TF_TOKEN`) locally when running Terraform against the remote backend.

## GitHub Actions secrets (documented)

| Secret | Used by | Purpose |
| --- | --- | --- |
| `TF_API_TOKEN` | `infra.yml` | Terraform Cloud (HCP Terraform) API token for the `cloud` backend |
| `AWS_TF_ROLE_ARN` | `infra.yml` | IAM role ARN for Terraform AWS operations via GitHub OIDC (`configure-aws-credentials`) |
| `AWS_SAGEMAKER_ROLE_ARN` | `ml-pipeline.yml` | IAM role ARN for SageMaker pipeline CLI / boto3 (OIDC) |

Configure a **GitHub Environment** named `production` with required reviewers if you use the gated `terraform-apply` job in `infra.yml`.

If you name roles differently, update the workflows to match. For a first bootstrap where the role only exists after Terraform creates it, apply once from a workstation, then store your Terraform OIDC role ARN as `AWS_TF_ROLE_ARN` (or keep a dedicated bootstrap role for cold start).

### Repository variables (GitHub **Settings → Secrets and variables → Actions → Variables**)

| Variable | Used by | Purpose |
| --- | --- | --- |
| `AWS_REGION` | `infra.yml`, `ml-pipeline.yml` | AWS region (workflows default to `ca-central-1` if unset) |
| `TERRAFORM_VERSION` | `infra.yml` | Optional; Terraform CLI version for `setup-terraform` (default `1.5.7`) |
| `MODEL_PACKAGE_GROUP_NAME` | `ml-pipeline.yml` | Model package group (e.g. `LogAnomalyDetectors`); must match `pipeline/definition.py` |
| `SAGEMAKER_PIPELINE_NAME` | `ml-pipeline.yml` | SageMaker Pipeline name (defaults to `log-anomaly-detection-pipeline` if unset) |
| `SAGEMAKER_ENDPOINT_NAME` | `ml-pipeline.yml` | Live endpoint to update after approval (e.g. Terraform output) |
| `SAGEMAKER_EXECUTION_ROLE_ARN` | `ml-pipeline.yml` | SageMaker execution role passed to `CreateModel` (not the OIDC role) |
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

## Git (first-time setup)

Initial commit and default branch **`develop`**:

```bash
chmod +x scripts/init-git.sh
./scripts/init-git.sh
```

Or manually:

```bash
git init -b develop
git add -A
git commit -m "Initial commit"
git remote add origin <YOUR_REPO_HTTPS_OR_SSH>
git push -u origin develop
```

On GitHub: **Settings → General → Default branch** → set to `develop`. Workflows run on **`main`** and **`develop`**; the gated `terraform-apply` job still runs only on pushes to **`main`**.

## License

Provided as sample infrastructure and application code; apply your organization’s policies before production use.
