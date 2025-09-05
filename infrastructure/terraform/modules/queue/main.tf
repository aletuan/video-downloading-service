# Queue Module - SQS for Celery task processing
# Optimized for development with cost-effective settings

# Random suffix for unique queue names
resource "random_id" "queue_suffix" {
  byte_length = 4
}

# Main SQS Queue for Celery tasks
resource "aws_sqs_queue" "main" {
  name                      = "${var.project_name}-${var.environment}-main-queue-${random_id.queue_suffix.hex}"
  delay_seconds            = 0
  max_message_size         = 262144  # 256KB (max allowed)
  message_retention_seconds = 1209600 # 14 days
  receive_wait_time_seconds = 20      # Long polling for cost optimization
  visibility_timeout_seconds = 300    # 5 minutes for task processing
  
  # Dead letter queue configuration
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })

  # Server-side encryption
  kms_master_key_id                 = "alias/aws/sqs"
  kms_data_key_reuse_period_seconds = 300

  tags = {
    Name        = "${var.project_name}-${var.environment}-main-queue"
    Environment = var.environment
    Purpose     = "celery-main-queue"
  }
}

# Dead Letter Queue for failed messages
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project_name}-${var.environment}-dlq-${random_id.queue_suffix.hex}"
  message_retention_seconds = 1209600 # 14 days retention for failed messages
  receive_wait_time_seconds = 20      # Long polling
  
  # Server-side encryption
  kms_master_key_id                 = "alias/aws/sqs"
  kms_data_key_reuse_period_seconds = 300

  tags = {
    Name        = "${var.project_name}-${var.environment}-dlq"
    Environment = var.environment
    Purpose     = "celery-dead-letter-queue"
  }
}

# SQS Queue Policy for ECS task access
resource "aws_sqs_queue_policy" "main" {
  queue_url = aws_sqs_queue.main.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = var.ecs_task_role_arn
        }
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:ChangeMessageVisibility",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.main.arn
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# SQS Queue Policy for DLQ access
resource "aws_sqs_queue_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = var.ecs_task_role_arn
        }
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:ChangeMessageVisibility",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.dlq.arn
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# CloudWatch Alarms for queue monitoring
resource "aws_cloudwatch_metric_alarm" "queue_depth" {
  alarm_name          = "${var.project_name}-${var.environment}-queue-depth-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ApproximateNumberOfVisibleMessages"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = var.queue_depth_alarm_threshold
  alarm_description   = "This alarm monitors SQS queue depth"
  alarm_actions       = var.enable_sns_notifications ? [aws_sns_topic.alerts[0].arn] : []

  dimensions = {
    QueueName = aws_sqs_queue.main.name
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-queue-depth-alarm"
  }
}

resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${var.project_name}-${var.environment}-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfVisibleMessages"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "0"
  alarm_description   = "This alarm monitors DLQ for failed messages"
  alarm_actions       = var.enable_sns_notifications ? [aws_sns_topic.alerts[0].arn] : []

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-dlq-messages-alarm"
  }
}

# Optional SNS topic for alerts (disabled by default for cost optimization)
resource "aws_sns_topic" "alerts" {
  count = var.enable_sns_notifications ? 1 : 0
  name  = "${var.project_name}-${var.environment}-queue-alerts"

  kms_master_key_id = "alias/aws/sns"

  tags = {
    Name = "${var.project_name}-${var.environment}-queue-alerts"
  }
}

# Systems Manager Parameters for queue configuration
resource "aws_ssm_parameter" "queue_url" {
  name        = "/${var.project_name}/${var.environment}/queue/main_url"
  description = "Main SQS queue URL for Celery"
  type        = "String"
  value       = aws_sqs_queue.main.url

  tags = {
    Name = "${var.project_name}-${var.environment}-queue-url"
  }
}

resource "aws_ssm_parameter" "queue_name" {
  name        = "/${var.project_name}/${var.environment}/queue/main_name"
  description = "Main SQS queue name for Celery"
  type        = "String"
  value       = aws_sqs_queue.main.name

  tags = {
    Name = "${var.project_name}-${var.environment}-queue-name"
  }
}

resource "aws_ssm_parameter" "dlq_url" {
  name        = "/${var.project_name}/${var.environment}/queue/dlq_url"
  description = "Dead letter queue URL"
  type        = "String"
  value       = aws_sqs_queue.dlq.url

  tags = {
    Name = "${var.project_name}-${var.environment}-dlq-url"
  }
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}