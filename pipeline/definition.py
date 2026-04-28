"""
SageMaker Pipeline: preprocess (SKLearn) -> train (Isolation Forest) -> evaluate (F1) -> condition -> register.

Run from repository root so ``source_dir="pipeline"`` and ``source_dir="training"`` resolve.
"""

from __future__ import annotations

import logging
import os

from sagemaker.inputs import TrainingInput
from sagemaker.processing import ProcessingInput, ProcessingOutput
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.sklearn.estimator import SKLearn
from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.workflow.condition_step import ConditionStep
from sagemaker.workflow.conditions import ConditionGreaterThanOrEqualTo
from sagemaker.workflow.functions import Join, JsonGet
from sagemaker.workflow.parameters import ParameterString
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.step_collections import RegisterModel
from sagemaker.workflow.steps import ProcessingStep, TrainingStep

logger = logging.getLogger(__name__)


def _pipeline_session() -> PipelineSession:
    """Build a ``PipelineSession`` (required for ``processor.run()`` → ``ProcessingStep(step_args=...)``).

    Set ``SAGEMAKER_DEFAULT_BUCKET`` to an existing bucket (typically Terraform
    ``aws_s3_bucket.processed_features`` name). Narrow CI/GitHub IAM roles rarely have ``s3:CreateBucket``
    on the auto-generated SageMaker bucket, so upserts may fail unless this is set.
    """
    explicit = (os.environ.get("SAGEMAKER_DEFAULT_BUCKET") or "").strip()
    if os.environ.get("GITHUB_ACTIONS") == "true" and not explicit:
        raise RuntimeError(
            "Set Actions variable or secret SAGEMAKER_DEFAULT_BUCKET to your pipeline root S3 bucket name "
            "(Terraform output s3_processed_features_bucket_name, e.g. <project>-processed-features). "
            "That prevents the SageMaker SDK from provisioning the account-wide sagemaker-{region}-{account} "
            "bucket, which OIDC deploy roles are usually not allowed to create."
        )
    if explicit:
        return PipelineSession(default_bucket=explicit)
    return PipelineSession()


def build_pipeline(execution_role_arn: str) -> Pipeline:
    """Construct the log-anomaly SageMaker Pipeline (SDK 2.x)."""
    role = execution_role_arn.strip()
    if not role:
        raise ValueError("execution_role_arn must be a non-empty SageMaker execution role ARN.")

    sess = _pipeline_session()

    default_bucket = sess.default_bucket()
    if not default_bucket:
        raise RuntimeError("SageMaker default_bucket is unavailable; configure the session or account defaults.")

    input_data_uri = ParameterString(
        name="InputDataURI",
        default_value=f"s3://{default_bucket}/raw/",
    )
    output_uri = ParameterString(
        name="OutputURI",
        default_value=f"s3://{default_bucket}/processed/",
    )
    model_package_group_name = ParameterString(
        name="ModelPackageGroupName",
        default_value="LogAnomalyDetectors",
    )

    sklearn_processor = SKLearnProcessor(
        framework_version="1.2-1",
        instance_type="ml.m5.large",
        instance_count=1,
        base_job_name="log-anomaly-preprocess",
        role=role,
        sagemaker_session=sess,
    )

    preprocess_step_args = sklearn_processor.run(
        code="pipeline/preprocess.py",
        inputs=[
            ProcessingInput(
                source=input_data_uri,
                destination="/opt/ml/processing/input/raw",
            ),
        ],
        outputs=[
            ProcessingOutput(
                output_name="processed",
                source="/opt/ml/processing/output",
                destination=output_uri,
            ),
        ],
        arguments=[],
        wait=False,
    )
    preprocess_step = ProcessingStep(
        name="EngineerLogFeatures",
        step_args=preprocess_step_args,
    )

    estimator = SKLearn(
        entry_point="train.py",
        source_dir="training",
        framework_version="1.2-1",
        py_version="py3",
        role=role,
        instance_count=1,
        instance_type="ml.m5.xlarge",
        volume_size=30,
        max_run=60 * 120,
        use_spot_instances=True,
        max_wait=3600,
        sagemaker_session=sess,
        base_job_name="log-anomaly-train-iforest",
    )

    train_step = TrainingStep(
        name="TrainIsolationForest",
        estimator=estimator,
        inputs={
            "train": TrainingInput(
                s3_data=preprocess_step.properties.ProcessingOutputConfig.Outputs["processed"].S3Output.S3Uri,
                content_type="text/csv",
            ),
        },
    )

    evaluation_report = PropertyFile(
        name="EvaluationReport",
        output_name="evaluation",
        path="evaluation.json",
    )

    evaluate_processor = SKLearnProcessor(
        framework_version="1.2-1",
        instance_type="ml.m5.large",
        instance_count=1,
        base_job_name="log-anomaly-evaluate",
        role=role,
        sagemaker_session=sess,
    )

    evaluate_step_args = evaluate_processor.run(
        code="pipeline/evaluate.py",
        inputs=[
            ProcessingInput(
                source=train_step.properties.ModelArtifacts.S3ModelArtifacts,
                destination="/opt/ml/processing/model",
            ),
            ProcessingInput(
                source=Join(
                    on="/",
                    values=[
                        preprocess_step.properties.ProcessingOutputConfig.Outputs["processed"].S3Output.S3Uri,
                        "holdout",
                        "eval.csv",
                    ],
                ),
                destination="/opt/ml/processing/holdout",
            ),
        ],
        outputs=[
            ProcessingOutput(
                output_name="evaluation",
                source="/opt/ml/processing/evaluation",
                destination=Join(on="/", values=[output_uri, "evaluation"]),
            ),
        ],
        arguments=[],
        wait=False,
    )
    evaluate_step = ProcessingStep(
        name="EvaluateAnomalyF1",
        step_args=evaluate_step_args,
        property_files=[evaluation_report],
    )

    register_model = RegisterModel(
        name="ModelRegistrationStep",
        estimator=estimator,
        model_data=train_step.properties.ModelArtifacts.S3ModelArtifacts,
        content_types=["text/csv", "application/json"],
        response_types=["application/json"],
        inference_instances=["ml.t2.medium"],
        transform_instances=["ml.m5.large"],
        model_package_group_name=model_package_group_name,
        approval_status="PendingManualApproval",
    )

    f1_gate = ConditionGreaterThanOrEqualTo(
        left=JsonGet(
            step_name=evaluate_step.name,
            property_file=evaluation_report,
            json_path="f1_score",
        ),
        right=0.75,
    )

    condition_step = ConditionStep(
        name="RegisterIfF1AtLeast075",
        conditions=[f1_gate],
        if_steps=list(register_model.steps),
        else_steps=[],
        depends_on=[evaluate_step.name],
    )

    pipeline = Pipeline(
        name="log-anomaly-detection-pipeline",
        parameters=[input_data_uri, output_uri, model_package_group_name],
        steps=[
            preprocess_step,
            train_step,
            evaluate_step,
            condition_step,
        ],
        sagemaker_session=sess,
    )

    logger.info("Pipeline '%s' definition built with default bucket s3://%s", pipeline.name, default_bucket)
    return pipeline


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    role_arn = os.environ["SAGEMAKER_ROLE_ARN"]
    pipeline = build_pipeline(role_arn)
    logger.info("Upserting pipeline with execution role from SAGEMAKER_ROLE_ARN")
    pipeline.upsert(role_arn=role_arn)
    execution = pipeline.start()
    logger.info("Started pipeline execution: %s", execution.describe().get("PipelineExecutionArn", execution))
