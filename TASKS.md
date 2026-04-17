# AWS Log Anomaly MLOps — Build Tasks

> **Instructions for Cursor:** Before starting any task, read this file.
> After completing any task, mark it `[x]`. Never mark an item complete
> unless the file was fully created and is non-empty.

---

## Phase 1: Repo Structure
- [x] Create root directory scaffold (`aws-log-anomaly-mlops/`)
- [x] Create `.gitignore` (Python, Terraform, macOS, IDE ignores)
- [x] Create `README.md` skeleton (project overview, setup steps, secrets list)

---

## Phase 2: Terraform
- [x] Create `terraform/backend.tf` (HCP Terraform remote state backend)
- [x] Create `terraform/variables.tf` (region, project name, bucket names, endpoint name)
- [x] Create `terraform/main.tf` (AWS provider config)
- [x] Create `terraform/s3.tf` (raw logs bucket, processed features bucket, model artifacts bucket)
- [x] Create `terraform/iam.tf` (GitHub OIDC role, SageMaker execution role)
- [x] Create `terraform/sagemaker.tf` (model, endpoint config, endpoint)
- [x] Create `terraform/cloudwatch.tf` (pipeline log group, endpoint error alarm, SNS topic)
- [x] Create `terraform/outputs.tf` (S3 bucket names/ARNs, endpoint name/ARN, role ARNs, SNS topic ARN)

---

## Phase 3: ML Pipeline
- [x] Create `pipeline/definition.py` (SKLearn preprocess/train/evaluate, F1 condition, model registry; `log-anomaly-detection-pipeline`)
- [x] Create `training/train.py` (Isolation Forest, `features.csv` schema, validation metrics → `/opt/ml/output/metrics.json`)
- [x] Create `inference/inference.py` (JSON `instances`, `expected_features`, structured predictions)

---

## Phase 4: GitHub Actions
- [x] Create `.github/workflows/infra.yml` (path triggers, plan + PR comment, saved plan, gated apply, HCP + OIDC)
- [x] Create `.github/workflows/ml-pipeline.yml` (path/push + dispatch, OIDC, upsert/start, poll, approve & deploy)

---

## Phase 5: Validation
- [x] `terraform fmt` passes with no changes
- [x] `terraform validate` passes with no errors
- [x] `pipeline/definition.py` runs without import errors
- [x] `training/train.py` runs without import errors
- [x] All required GitHub Actions secrets documented in `README.md`
- [x] All Terraform variables have descriptions and types defined

---

## Progress Summary
- Total tasks: 22
- Completed: 22
- Remaining: 0
