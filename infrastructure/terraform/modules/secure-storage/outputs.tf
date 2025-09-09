# Outputs for Secure Storage Module

output "secure_config_bucket_name" {
  description = "Name of the secure configuration S3 bucket"
  value       = aws_s3_bucket.secure_config.id
}

output "secure_config_bucket_arn" {
  description = "ARN of the secure configuration S3 bucket"
  value       = aws_s3_bucket.secure_config.arn
}

output "secure_config_bucket_domain_name" {
  description = "Domain name of the secure configuration S3 bucket"
  value       = aws_s3_bucket.secure_config.bucket_domain_name
}

output "access_logs_bucket_name" {
  description = "Name of the access logs S3 bucket"
  value       = aws_s3_bucket.access_logs.id
}

output "access_logs_bucket_arn" {
  description = "ARN of the access logs S3 bucket"
  value       = aws_s3_bucket.access_logs.arn
}

output "cloudwatch_log_group_name" {
  description = "Name of the CloudWatch log group for S3 access monitoring"
  value       = aws_cloudwatch_log_group.s3_access.name
}

output "cloudwatch_log_group_arn" {
  description = "ARN of the CloudWatch log group for S3 access monitoring"
  value       = aws_cloudwatch_log_group.s3_access.arn
}

output "security_alerts_topic_arn" {
  description = "ARN of the SNS topic for security alerts"
  value       = aws_sns_topic.security_alerts.arn
}

output "cookie_directory_path" {
  description = "S3 path for cookie files"
  value       = "s3://${aws_s3_bucket.secure_config.id}/cookies/"
}

output "eventbridge_rule_arn" {
  description = "ARN of the EventBridge rule for S3 object events"
  value       = aws_cloudwatch_event_rule.s3_object_events.arn
}

# Configuration values for application
output "s3_config" {
  description = "S3 configuration for application use"
  value = {
    bucket_name                = aws_s3_bucket.secure_config.id
    bucket_arn                 = aws_s3_bucket.secure_config.arn
    cookie_path_prefix         = "cookies/"
    active_cookie_key          = "cookies/youtube-cookies-active.txt"
    backup_cookie_key          = "cookies/youtube-cookies-backup.txt"
    metadata_key               = "cookies/metadata.json"
    region                     = data.aws_region.current.name
    versioning_enabled         = true
    encryption_enabled         = true
    access_logging_enabled     = true
    lifecycle_policy_enabled   = true
  }
  sensitive = false
}

# Security and monitoring configuration
output "security_config" {
  description = "Security and monitoring configuration"
  value = {
    access_logs_bucket         = aws_s3_bucket.access_logs.id
    cloudwatch_log_group       = aws_cloudwatch_log_group.s3_access.name
    security_alerts_topic      = aws_sns_topic.security_alerts.arn
    eventbridge_rule           = aws_cloudwatch_event_rule.s3_object_events.name
    monitoring_enabled         = true
    encryption_algorithm       = "AES256"
    versioning_enabled         = true
  }
  sensitive = false
}

# IAM configuration for ECS task
output "iam_config" {
  description = "IAM configuration for ECS task integration"
  value = {
    allowed_actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucket"
    ]
    resource_arns = [
      aws_s3_bucket.secure_config.arn,
      "${aws_s3_bucket.secure_config.arn}/cookies/*"
    ]
    conditions = {
      StringLike = {
        "s3:prefix" = "cookies/*"
      }
    }
  }
  sensitive = false
}