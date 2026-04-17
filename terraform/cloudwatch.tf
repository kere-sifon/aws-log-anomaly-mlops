# CloudWatch log group for SageMaker pipeline logging, endpoint error alarm, and SNS notifications.

resource "aws_sns_topic" "log_anomaly_alerts" {
  name = "${var.project_name}-alerts"

  tags = merge(local.default_tags, {
    Name = "${var.project_name}-alerts"
  })
}

# Allows CloudWatch metric alarms to notify this topic (required for alarm_actions).
data "aws_iam_policy_document" "sns_cloudwatch_publish" {
  statement {
    sid    = "AllowCloudWatchAlarmPublish"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.log_anomaly_alerts.arn]
  }
}

resource "aws_sns_topic_policy" "log_anomaly_alerts" {
  arn    = aws_sns_topic.log_anomaly_alerts.arn
  policy = data.aws_iam_policy_document.sns_cloudwatch_publish.json
}

resource "aws_cloudwatch_log_group" "sagemaker_pipeline" {
  name              = "/aws/sagemaker/${var.project_name}-pipeline"
  retention_in_days = 30

  tags = merge(local.default_tags, {
    Name = "${var.project_name}-sagemaker-pipeline-logs"
  })
}

# Fires when server-side invocation failures exceed five within a single 5-minute window.
resource "aws_cloudwatch_metric_alarm" "sagemaker_endpoint_invocation_errors" {
  alarm_name          = "${var.project_name}-sm-invocation-errors-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Invocation5XXErrors"
  namespace           = "AWS/SageMaker"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_description   = "SageMaker endpoint invocation 5xx count exceeded 5 in one 5-minute period."

  dimensions = {
    EndpointName = aws_sagemaker_endpoint.log_anomaly_detector.name
    VariantName  = "primary"
  }

  alarm_actions = [aws_sns_topic.log_anomaly_alerts.arn]

  tags = merge(local.default_tags, {
    Name = "${var.project_name}-sm-invocation-errors-alarm"
  })
}
