# Secure Storage Module for YouTube Downloader
# Provides encrypted S3 bucket for sensitive configuration files including cookies

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }
}

# Generate random suffix for bucket name uniqueness
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# S3 bucket for secure cookie storage
resource "aws_s3_bucket" "secure_config" {
  bucket = "${var.project_name}-${var.environment}-secure-config-${random_id.bucket_suffix.hex}"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-secure-config"
    Purpose     = "Secure storage for sensitive configuration files"
    DataType    = "Sensitive"
    Encryption  = "Required"
  })
}

# Server-side encryption configuration
resource "aws_s3_bucket_server_side_encryption_configuration" "secure_config" {
  bucket = aws_s3_bucket.secure_config.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Bucket versioning for cookie file history
resource "aws_s3_bucket_versioning" "secure_config" {
  bucket = aws_s3_bucket.secure_config.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "secure_config" {
  bucket = aws_s3_bucket.secure_config.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 bucket policy - restrict access to ECS task role only
resource "aws_s3_bucket_policy" "secure_config" {
  bucket = aws_s3_bucket.secure_config.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RestrictToECSTaskRole"
        Effect = "Allow"
        Principal = {
          AWS = var.ecs_task_role_arn
        }
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion"
        ]
        Resource = "${aws_s3_bucket.secure_config.arn}/cookies/*"
      },
      {
        Sid    = "AllowECSTaskRoleListBucket"
        Effect = "Allow"
        Principal = {
          AWS = var.ecs_task_role_arn
        }
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.secure_config.arn
        Condition = {
          StringLike = {
            "s3:prefix" = "cookies/*"
          }
        }
      },
      {
        Sid    = "DenyAllOtherAccess"
        Effect = "Deny"
        NotPrincipal = {
          AWS = [
            var.ecs_task_role_arn,
            "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
          ]
        }
        Action   = "s3:*"
        Resource = [
          aws_s3_bucket.secure_config.arn,
          "${aws_s3_bucket.secure_config.arn}/*"
        ]
      }
    ]
  })
}

# S3 bucket for access logging
resource "aws_s3_bucket" "access_logs" {
  bucket = "${var.project_name}-${var.environment}-secure-config-logs-${random_id.bucket_suffix.hex}"

  tags = merge(var.tags, {
    Name    = "${var.project_name}-${var.environment}-secure-config-logs"
    Purpose = "Access logs for secure configuration bucket"
  })
}

# Block public access for logs bucket
resource "aws_s3_bucket_public_access_block" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Server-side encryption for logs bucket
resource "aws_s3_bucket_server_side_encryption_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Enable access logging for the main bucket
resource "aws_s3_bucket_logging" "secure_config" {
  bucket = aws_s3_bucket.secure_config.id

  target_bucket = aws_s3_bucket.access_logs.id
  target_prefix = "access-logs/"
}

# Lifecycle configuration for automatic cleanup
resource "aws_s3_bucket_lifecycle_configuration" "secure_config" {
  bucket = aws_s3_bucket.secure_config.id

  rule {
    id     = "cookie_file_lifecycle"
    status = "Enabled"

    # Keep current versions for 90 days
    expiration {
      days = 90
    }

    # Keep non-current versions for 30 days
    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    # Delete incomplete multipart uploads after 7 days
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "access_logs_lifecycle"
    status = "Enabled"

    filter {
      prefix = "access-logs/"
    }

    # Keep access logs for 1 year
    expiration {
      days = 365
    }
  }
}

# Lifecycle configuration for logs bucket
resource "aws_s3_bucket_lifecycle_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  rule {
    id     = "logs_cleanup"
    status = "Enabled"

    # Keep logs for 1 year
    expiration {
      days = 365
    }

    # Delete incomplete multipart uploads after 3 days
    abort_incomplete_multipart_upload {
      days_after_initiation = 3
    }
  }
}

# CloudWatch Log Group for S3 access monitoring
resource "aws_cloudwatch_log_group" "s3_access" {
  name              = "/aws/s3/${aws_s3_bucket.secure_config.id}"
  retention_in_days = 90

  tags = merge(var.tags, {
    Name    = "${var.project_name}-${var.environment}-s3-access-logs"
    Purpose = "S3 access monitoring"
  })
}

# EventBridge rule for S3 object events
resource "aws_cloudwatch_event_rule" "s3_object_events" {
  name        = "${var.project_name}-${var.environment}-s3-object-events"
  description = "Capture S3 object events for secure config bucket"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created", "Object Deleted"]
    detail = {
      bucket = {
        name = [aws_s3_bucket.secure_config.id]
      }
    }
  })

  tags = var.tags
}

# CloudWatch Log Stream for EventBridge
resource "aws_cloudwatch_log_stream" "s3_events" {
  name           = "s3-object-events"
  log_group_name = aws_cloudwatch_log_group.s3_access.name
}

# EventBridge target to send events to CloudWatch Logs
resource "aws_cloudwatch_event_target" "s3_logs" {
  rule      = aws_cloudwatch_event_rule.s3_object_events.name
  target_id = "S3EventsToCloudWatchLogs"
  arn       = aws_cloudwatch_log_group.s3_access.arn
}

# IAM role for EventBridge to write to CloudWatch Logs
resource "aws_iam_role" "eventbridge_logs" {
  name = "${var.project_name}-${var.environment}-eventbridge-s3-logs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# IAM policy for EventBridge to write to CloudWatch Logs
resource "aws_iam_role_policy" "eventbridge_logs" {
  name = "${var.project_name}-${var.environment}-eventbridge-logs-policy"
  role = aws_iam_role.eventbridge_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.s3_access.arn}:*"
      }
    ]
  })
}

# Notification topic for security alerts
resource "aws_sns_topic" "security_alerts" {
  name = "${var.project_name}-${var.environment}-secure-config-alerts"

  tags = merge(var.tags, {
    Name    = "${var.project_name}-${var.environment}-security-alerts"
    Purpose = "Security alerts for secure configuration bucket"
  })
}

# CloudWatch alarm for unexpected S3 access patterns
resource "aws_cloudwatch_metric_alarm" "unusual_access" {
  alarm_name          = "${var.project_name}-${var.environment}-unusual-s3-access"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "NumberOfObjects"
  namespace           = "AWS/S3"
  period              = "300"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "This metric monitors unusual access patterns to secure config bucket"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  dimensions = {
    BucketName = aws_s3_bucket.secure_config.id
  }

  tags = var.tags
}