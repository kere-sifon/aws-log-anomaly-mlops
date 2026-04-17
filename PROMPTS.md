# AWS Log Anomaly MLOps — Cursor Scaffold Prompts

> **How to use this file:**
> Run each prompt in order inside Cursor.
> Wait for Cursor to finish and update TASKS.md before moving to the next prompt.
> Do not skip prompts — each one builds on the previous.

---

## Prompt 1 — Repo Scaffold

```
Read TASKS.md before starting.

Create a GitHub repository scaffold for an AWS MLOps pipeline project called
`aws-log-anomaly-mlops`. The stack is Terraform + Python SageMaker SDK +
GitHub Actions.

Use this directory structure:

aws-log-anomaly-mlops/
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── s3.tf
│   ├── iam.tf
│   ├── sagemaker.tf
│   ├── cloudwatch.tf
│   └── backend.tf
├── pipeline/
│   └── definition.py
├── training/
│   └── train.py
├── inference/
│   └── inference.py
├── .github/
│   └── workflows/
│       ├── infra.yml
│       └── ml-pipeline.yml
├── .gitignore
└── README.md

Rules:
- Terraform AWS provider version ~> 5.0, region var defaulting to ca-central-1
- Use OIDC for GitHub Actions IAM authentication, no static credentials
- HCP Terraform (app.terraform.io) as the remote state backend
- The ML model is Isolation Forest from scikit-learn for log anomaly detection
- SageMaker training uses ml.m5.xlarge with spot instances enabled
- SageMaker endpoint uses ml.t2.medium
- Create all files with realistic placeholder content, not empty files
- Add comments explaining each resource
- Every Terraform variable must have a description and type
- Every AWS resource must have a tags block with: Project, Environment, ManagedBy

After completing this task, update TASKS.md by marking every completed
item [x]. Do not mark items complete unless the file was actually created
and is non-empty. Show me the updated Phase 1 section of TASKS.md.
```

---

## Prompt 2 — Terraform IAM + OIDC

```
Read TASKS.md before starting. Check that Phase 1 items are all [x] before proceeding.

In the `terraform/iam.tf` file, create all IAM roles needed for this MLOps project:

1. `github_actions_role` — OIDC trust policy for GitHub Actions from the repo
   `<YOUR_GITHUB_USERNAME>/aws-log-anomaly-mlops`. Permissions needed:
   - sagemaker:* on all pipeline, model, and endpoint resources
   - s3:GetObject, PutObject, DeleteObject scoped to project S3 buckets only
   - iam:PassRole scoped to the SageMaker execution role ARN only
   - ecr:GetAuthorizationToken, BatchGetImage

2. `sagemaker_execution_role` — trusted by sagemaker.amazonaws.com. Permissions:
   - S3 full access scoped to project buckets only (no wildcard bucket ARN)
   - CloudWatch Logs: CreateLogGroup, CreateLogStream, PutLogEvents
   - ECR: GetAuthorizationToken, BatchGetImage, GetDownloadUrlForLayer
   - SageMaker full access

Rules:
- No wildcard * on resource ARNs — scope every policy to named resources
- Use least-privilege throughout
- Reference bucket ARNs from s3.tf outputs, not hardcoded strings
- Output both role ARNs as Terraform outputs

After completing this task, update TASKS.md by marking the iam.tf item [x].
Show me the updated Phase 2 section of TASKS.md.
```

---

## Prompt 3 — Terraform SageMaker Resources

```
Read TASKS.md before starting. Check that terraform/iam.tf is marked [x] before proceeding.

In `terraform/sagemaker.tf`, define the following SageMaker resources:

1. `aws_sagemaker_model` — named `log-anomaly-model`, references the
   sklearn built-in container image for the ca-central-1 region, model
   artifacts path sourced from the S3 model artifacts bucket output

2. `aws_sagemaker_endpoint_configuration` — named
   `log-anomaly-endpoint-config`, uses ml.t2.medium, single production
   variant with initial_instance_count = 1

3. `aws_sagemaker_endpoint` — named `log-anomaly-detector-endpoint`,
   references the endpoint config above

Rules:
- Add a lifecycle block on the endpoint to ignore_changes on endpoint_config_name
  (endpoint model swaps are handled by ml-pipeline.yml, not Terraform)
- Tag all resources with: Project, Environment, ManagedBy
- Reference the sagemaker_execution_role ARN from iam.tf outputs
- Output the endpoint name and endpoint ARN

After completing this task, update TASKS.md by marking the sagemaker.tf
item [x]. Show me the updated Phase 2 section of TASKS.md.
```

---

## Prompt 4 — Terraform S3, CloudWatch, Outputs

```
Read TASKS.md before starting.

Complete the remaining Terraform files:

1. `terraform/s3.tf` — Create three S3 buckets:
   - `<project-name>-raw-logs` — landing zone for incoming log files
   - `<project-name>-processed-features` — output from preprocessing step
   - `<project-name>-model-artifacts` — SageMaker training output and model storage
   Enable versioning on all three. Block all public access. Add lifecycle rules
   to expire objects older than 90 days in the raw bucket.

2. `terraform/cloudwatch.tf` — Create:
   - A CloudWatch Log Group `/aws/sagemaker/log-anomaly-pipeline` with 30 day retention
   - A CloudWatch Alarm that triggers when SageMaker endpoint invocation errors
     exceed 5 in a 5-minute period
   - An SNS topic `log-anomaly-alerts` that the alarm publishes to

3. `terraform/outputs.tf` — Output:
   - All three S3 bucket names and ARNs
   - SageMaker endpoint name and ARN
   - GitHub Actions IAM role ARN
   - SageMaker execution role ARN
   - SNS topic ARN

Rules:
- Use var.project_name to prefix all resource names — no hardcoded names
- Tag all resources with: Project, Environment, ManagedBy

After completing this task, update TASKS.md by marking s3.tf, cloudwatch.tf,
and outputs.tf items [x]. Show me the updated Phase 2 section of TASKS.md.
```

---

## Prompt 5 — SageMaker Pipeline Definition

```
Read TASKS.md before starting. Check that Phase 2 items are all [x] before proceeding.

In `pipeline/definition.py`, create a SageMaker Pipeline using the
SageMaker Python SDK with these steps:

1. ProcessingStep — SKLearnProcessor, reads raw logs from S3
   (s3://LOG_BUCKET/raw/), outputs feature CSV to S3
   (s3://LOG_BUCKET/processed/)

2. TrainingStep — SKLearn estimator, entry point `training/train.py`,
   framework version 1.2-1, instance type ml.m5.xlarge, spot instances
   enabled with max_wait=3600, trains Isolation Forest on processed features

3. EvaluationStep (ProcessingStep) — runs a script that calculates
   anomaly detection F1 score against a labeled holdout set, writes
   evaluation.json to S3

4. ConditionStep — registers the model only if F1 score >= 0.75

5. ModelRegistrationStep — registers to model package group
   `LogAnomalyDetectors` with approval status `PendingManualApproval`

Rules:
- Accept pipeline parameters: InputDataURI, OutputURI, ModelPackageGroupName
- Pipeline name: `log-anomaly-detection-pipeline`
- Use logging module throughout, not print statements
- Include a `if __name__ == "__main__"` block that upserts and starts the pipeline
- Read the SageMaker execution role ARN from environment variable SAGEMAKER_ROLE_ARN

After completing this task, update TASKS.md by marking pipeline/definition.py
[x]. Show me the updated Phase 3 section of TASKS.md.
```

---

## Prompt 6 — Training Script

```
Read TASKS.md before starting.

In `training/train.py`, write a SageMaker-compatible training script that:

1. Reads feature CSV from `/opt/ml/input/data/train/features.csv`
   Columns: timestamp, cpu_usage, memory_usage, error_rate,
   request_latency_ms, log_level_encoded

2. Trains an Isolation Forest model:
   - contamination=0.05 (overridable via --contamination arg)
   - n_estimators=100 (overridable via --n-estimators arg)
   - random_state=42

3. Evaluates on a validation split (80/20), outputs these metrics to
   `/opt/ml/output/metrics.json`:
   - anomaly_rate
   - f1_score (against synthetic labels where score < threshold = anomaly)
   - threshold used
   - training_samples count
   - validation_samples count

4. Saves the trained model to `/opt/ml/model/model.joblib`

Rules:
- Use argparse for all hyperparameters so SageMaker can pass them in
- Use logging module throughout, not print statements
- Handle missing or malformed CSV rows gracefully with logged warnings
- Use scikit-learn, pandas, joblib only — no other ML libraries

After completing this task, update TASKS.md by marking training/train.py
[x]. Show me the updated Phase 3 section of TASKS.md.
```

---

## Prompt 7 — Inference Script

```
Read TASKS.md before starting.

In `inference/inference.py`, write a SageMaker-compatible inference script
with these four required handler functions:

1. `model_fn(model_dir)` — loads model.joblib from model_dir,
   returns the loaded Isolation Forest model

2. `input_fn(request_body, content_type)` — accepts application/json,
   parses the instances array into a pandas DataFrame,
   raises ValueError for unsupported content types

3. `predict_fn(input_data, model)` — runs model.decision_function()
   for anomaly scores and model.predict() for labels (-1 anomaly, 1 normal),
   returns a dict with anomaly_scores and predictions arrays

4. `output_fn(prediction, accept)` — serializes the prediction dict
   to JSON for application/json accept type

Expected request shape:
{
  "instances": [
    { "cpu_usage": 0.91, "memory_usage": 0.74, "error_rate": 0.12,
      "request_latency_ms": 430, "log_level_encoded": 2 }
  ]
}

Expected response shape:
{
  "predictions": [
    { "anomaly_score": -0.43, "is_anomaly": true }
  ]
}

Rules:
- Use logging module throughout
- Handle missing feature columns gracefully with a clear error message
- No hardcoded feature column names — read from an expected_features list
  defined at the top of the file so it is easy to update

After completing this task, update TASKS.md by marking inference/inference.py
[x]. Show me the updated Phase 3 section of TASKS.md.
```

---

## Prompt 8 — ml-pipeline.yml GitHub Actions Workflow

```
Read TASKS.md before starting. Check that Phase 3 items are all [x] before proceeding.

Create `.github/workflows/ml-pipeline.yml`, a GitHub Actions workflow with
these requirements:

Triggers:
- Push to main branch when files under `training/` or `pipeline/` change
- Manual workflow_dispatch with an optional boolean input `force_retrain`

Job 1: `trigger-pipeline`
- Runs on ubuntu-latest
- Explicit permissions block: id-token: write, contents: read
- Authenticates to AWS using OIDC (secret: AWS_SAGEMAKER_ROLE_ARN, region ca-central-1)
- Installs boto3 and sagemaker Python packages
- Runs `python pipeline/definition.py` to upsert the pipeline definition
- Starts a pipeline execution via boto3 start_pipeline_execution()
- Outputs the pipeline_execution_arn as a job output

Job 2: `wait-for-pipeline`
- Depends on trigger-pipeline
- Polls pipeline execution status every 60 seconds using a Python inline script
- Times out after 30 minutes (max 30 iterations)
- Fails the workflow if pipeline status is Failed or Stopped
- Prints the final status to the workflow summary

Job 3: `approve-and-deploy`
- Depends on wait-for-pipeline, only runs if pipeline succeeded
- Approves the latest model package in the LogAnomalyDetectors group
  via boto3 update_model_package (ModelApprovalStatus: Approved)
- Updates the SageMaker endpoint to use the new approved model version
  via boto3 update_endpoint
- Writes a GitHub Actions job summary with:
  model package ARN, endpoint name, execution ARN, and timestamp

Rules:
- Pin all action versions (e.g. actions/checkout@v4)
- No hardcoded ARNs — use GitHub Actions secrets and vars throughout
- Use AWS_REGION and MODEL_PACKAGE_GROUP_NAME as repository variables
- Use AWS_SAGEMAKER_ROLE_ARN as a repository secret

After completing this task, update TASKS.md by marking ml-pipeline.yml [x].
Show me the updated Phase 4 section of TASKS.md.
```

---

## Prompt 9 — infra.yml GitHub Actions Workflow

```
Read TASKS.md before starting.

Create `.github/workflows/infra.yml`, a GitHub Actions workflow for
Terraform that:

Triggers:
- Push to main when any file under `terraform/` changes
- Pull request to main when any file under `terraform/` changes
- Manual workflow_dispatch

Job 1: `terraform-plan` (runs on both PR and push)
- ubuntu-latest
- Explicit permissions block: id-token: write, contents: read, pull-requests: write
- Authenticates to AWS via OIDC using secret AWS_TF_ROLE_ARN
- Authenticates to HCP Terraform using secret TF_API_TOKEN
- Steps: checkout → setup-terraform → init → fmt check → validate → plan
- Saves plan output to a file plan.tfplan
- On pull requests: posts the full plan output as a PR comment using
  actions/github-script@v7

Job 2: `terraform-apply` (runs on push to main only)
- Depends on terraform-plan
- Uses environment: production (requires a manual reviewer approval in GitHub)
- Runs terraform apply -auto-approve using the saved plan.tfplan
- On failure: writes a failure summary to the GitHub Actions job summary

Rules:
- Pin all action versions
- No hardcoded values — use secrets and vars throughout
- Follow the same OIDC and HCP Terraform backend pattern as the
  aws-infra-templates repo
- Use hashicorp/setup-terraform@v3

After completing this task, update TASKS.md by marking infra.yml [x].
Show me the full updated TASKS.md file with all sections.
```

---

## Prompt 10 — Final Validation

```
Read TASKS.md. For every item marked [x], verify the corresponding file
exists in the project and is non-empty.

For any item where the file is missing or empty:
- Mark it [ ] again in TASKS.md
- Tell me exactly which file is missing and what needs to be fixed

Then run the following checks and report pass or fail for each:
1. All Terraform files have valid HCL syntax (check for unclosed blocks,
   missing equals signs, obvious syntax errors)
2. All Python files have valid imports (no references to packages not in
   requirements — scikit-learn, pandas, joblib, boto3, sagemaker)
3. Every GitHub Actions workflow has a permissions block on every job
4. No hardcoded AWS account IDs, access keys, or ARNs anywhere
5. All required secrets are listed in README.md

Update the Progress Summary in TASKS.md with the final completed count.
Show me the complete final TASKS.md.
```

---

## Quick Reference — Secrets to Configure in GitHub

Before running the workflows, add these in your GitHub repo under
Settings → Secrets and Variables:

| Name | Type | Description |
|---|---|---|
| `AWS_TF_ROLE_ARN` | Secret | IAM role ARN for Terraform OIDC |
| `AWS_SAGEMAKER_ROLE_ARN` | Secret | IAM role ARN for SageMaker pipeline |
| `TF_API_TOKEN` | Secret | HCP Terraform API token |
| `AWS_REGION` | Variable | `ca-central-1` |
| `MODEL_PACKAGE_GROUP_NAME` | Variable | `LogAnomalyDetectors` |
