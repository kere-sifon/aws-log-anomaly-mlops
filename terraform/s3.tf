# S3 buckets for raw ingestion, engineered features, and SageMaker model artifacts.
# Names use var.project_name only (per naming contract). Server-side encryption and
# versioning support reproducible training and audit trails.

resource "aws_s3_bucket" "raw_logs" {
  bucket = "${var.project_name}-raw-logs"

  tags = merge(local.default_tags, {
    Name = "${var.project_name}-raw-logs"
  })
}

resource "aws_s3_bucket_versioning" "raw_logs" {
  bucket = aws_s3_bucket.raw_logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_logs" {
  bucket = aws_s3_bucket.raw_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "raw_logs" {
  bucket = aws_s3_bucket.raw_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Landing zone: drop expired log objects after 90 days (current and noncurrent versions).
resource "aws_s3_bucket_lifecycle_configuration" "raw_logs" {
  bucket = aws_s3_bucket.raw_logs.id

  rule {
    id     = "expire-raw-older-than-90-days"
    status = "Enabled"

    filter {}

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }

  depends_on = [aws_s3_bucket_versioning.raw_logs]
}

resource "aws_s3_bucket" "processed_features" {
  bucket = "${var.project_name}-processed-features"

  tags = merge(local.default_tags, {
    Name = "${var.project_name}-processed-features"
  })
}

resource "aws_s3_bucket_versioning" "processed_features" {
  bucket = aws_s3_bucket.processed_features.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "processed_features" {
  bucket = aws_s3_bucket.processed_features.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "processed_features" {
  bucket = aws_s3_bucket.processed_features.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "model_artifacts" {
  bucket = "${var.project_name}-model-artifacts"

  tags = merge(local.default_tags, {
    Name = "${var.project_name}-model-artifacts"
  })
}

resource "aws_s3_bucket_versioning" "model_artifacts" {
  bucket = aws_s3_bucket.model_artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "model_artifacts" {
  bucket = aws_s3_bucket.model_artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "model_artifacts" {
  bucket = aws_s3_bucket.model_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Seeds a minimal gzip/tar object so SageMaker model creation has an existing artifact path before CI uploads trained models.
resource "aws_s3_object" "bootstrap_model_artifact" {
  bucket = aws_s3_bucket.model_artifacts.id
  key    = var.model_data_s3_object_key
  source = "${path.module}/files/bootstrap_model.tar.gz"
  etag   = filemd5("${path.module}/files/bootstrap_model.tar.gz")

  tags = merge(local.default_tags, {
    Name = "${var.project_name}-bootstrap-model-artifact"
  })
}
