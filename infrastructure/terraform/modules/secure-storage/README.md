# Secure Storage Module

This Terraform module creates a secure S3 bucket infrastructure for storing sensitive configuration files, specifically designed for YouTube downloader cookie management.

## Features

- **Encrypted S3 bucket** with AES-256 server-side encryption
- **Versioning enabled** for configuration file history
- **Access logging** for audit trails
- **Lifecycle policies** for automatic cleanup
- **IAM policies** restricting access to ECS task role only
- **CloudWatch monitoring** for security events
- **SNS alerts** for unusual access patterns

## Security

- All public access blocked
- Bucket policy restricts access to specified ECS task role
- Server-side encryption enabled by default
- Access logging to separate bucket
- CloudWatch monitoring for security events
- EventBridge integration for real-time alerts

## Usage

```hcl
module "secure_storage" {
  source = "./modules/secure-storage"

  project_name      = "youtube-downloader"
  environment       = "dev"
  ecs_task_role_arn = "arn:aws:iam::123456789012:role/youtube-downloader-task-role"

  # Optional configurations
  cookie_retention_days = 90
  version_retention_days = 30
  log_retention_days = 365
  
  tags = {
    Project = "youtube-downloader"
    Environment = "dev"
  }
}
```

## Directory Structure

The module creates the following S3 directory structure:

```
s3://bucket-name/
├── cookies/
│   ├── youtube-cookies-active.txt
│   ├── youtube-cookies-backup.txt
│   └── metadata.json
└── access-logs/
    └── (access log files)
```

## Outputs

- `secure_config_bucket_name` - Name of the secure configuration bucket
- `secure_config_bucket_arn` - ARN of the secure configuration bucket
- `cookie_directory_path` - S3 path for cookie files
- `security_alerts_topic_arn` - SNS topic for security alerts
- `s3_config` - Complete configuration object for application use

## Monitoring

The module sets up:

- CloudWatch log group for S3 access events
- EventBridge rule for object-level events
- CloudWatch alarms for unusual access patterns
- SNS topic for security alerts

## Compliance

- Encryption at rest and in transit
- Access logging for audit trails
- Versioning for data integrity
- Automated lifecycle management
- Least privilege access controls