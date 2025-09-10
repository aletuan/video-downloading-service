# Development Environment Outputs

# Account and Region Information
output "account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "AWS Region"
  value       = data.aws_region.current.name
}

# Networking Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.networking.public_subnet_ids
}

output "security_groups" {
  description = "Security group IDs"
  value = {
    ecs   = module.networking.ecs_security_group_id
    rds   = module.networking.rds_security_group_id
    redis = module.networking.redis_security_group_id
    alb   = module.networking.alb_security_group_id
  }
}

# Database Outputs
output "database_endpoint" {
  description = "PostgreSQL database endpoint"
  value       = module.database.postgres_endpoint
}

output "database_port" {
  description = "PostgreSQL database port"
  value       = module.database.postgres_port
}

output "database_name" {
  description = "PostgreSQL database name"
  value       = module.database.postgres_database_name
}

output "redis_endpoint" {
  description = "Redis cluster endpoint"
  value       = module.database.redis_endpoint
}

output "redis_port" {
  description = "Redis cluster port"
  value       = module.database.redis_port
}

# Storage Outputs
output "s3_bucket_name" {
  description = "S3 bucket name for video storage"
  value       = module.storage.s3_bucket_name
}

output "s3_bucket_region" {
  description = "S3 bucket region"
  value       = module.storage.s3_bucket_region
}

output "storage_configuration" {
  description = "Storage configuration summary"
  value       = module.storage.storage_configuration
}

# Compute Outputs
output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.compute.cluster_name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = module.compute.cluster_arn
}

output "app_service_name" {
  description = "FastAPI service name"
  value       = module.compute.app_service_name
}

output "worker_service_name" {
  description = "Celery worker service name"
  value       = module.compute.worker_service_name
}

output "log_groups" {
  description = "CloudWatch log group names"
  value = {
    app    = module.compute.app_log_group_name
    worker = module.compute.worker_log_group_name
  }
}

# Load Balancer Outputs
output "alb_dns_name" {
  description = "Application Load Balancer DNS name"
  value       = module.load_balancer.alb_dns_name
}

output "alb_endpoint" {
  description = "Application Load Balancer endpoint URL"
  value       = module.load_balancer.alb_endpoint
}

output "alb_zone_id" {
  description = "Application Load Balancer zone ID"
  value       = module.load_balancer.alb_zone_id
}

output "target_group_arn" {
  description = "Target group ARN"
  value       = module.load_balancer.target_group_arn
}

output "target_group_name" {
  description = "Target group name"
  value       = module.load_balancer.target_group_name
}

# Connection Information
output "database_connection_info" {
  description = "Database connection information"
  value = {
    endpoint = module.database.postgres_endpoint
    port     = module.database.postgres_port
    database = module.database.postgres_database_name
    username = module.database.postgres_username
  }
  sensitive = true
}

output "redis_connection_info" {
  description = "Redis connection information"
  value = {
    endpoint = module.database.redis_endpoint
    port     = module.database.redis_port
  }
}

# Secure Storage Outputs (Cookie Management)
output "secure_storage_bucket_name" {
  description = "Secure S3 bucket name for cookie management"
  value       = module.secure_storage.secure_config_bucket_name
}

output "secure_storage_bucket_arn" {
  description = "Secure S3 bucket ARN for cookie management"
  value       = module.secure_storage.secure_config_bucket_arn
}

output "cookie_directory_path" {
  description = "S3 path for cookie files"
  value       = module.secure_storage.cookie_directory_path
}

output "secure_storage_config" {
  description = "Complete secure storage configuration"
  value       = module.secure_storage.s3_config
}

# Systems Manager Parameters
output "parameter_store_keys" {
  description = "Systems Manager parameter names"
  value = {
    database_url      = aws_ssm_parameter.database_url.name
    redis_url        = aws_ssm_parameter.redis_url.name
    s3_bucket_name   = module.storage.s3_bucket_name_parameter
    s3_bucket_region = module.storage.s3_bucket_region_parameter
    cookie_encryption_key = aws_ssm_parameter.cookie_encryption_key.name
  }
}

# Cost Estimation
output "estimated_monthly_cost" {
  description = "Estimated monthly cost breakdown (USD)"
  value = {
    ecs_fargate = "~$14 (2 tasks x 0.25vCPU x 0.5GB)"
    rds_postgres = "~$12 (db.t3.micro single-AZ)"
    elasticache_redis = "~$11 (cache.t3.micro)"
    vpc_networking = "~$2 (no NAT gateway)"
    s3_storage = "~$1-2 (50GB standard)"
    cloudwatch_logs = "~$1 (7-day retention)"
    total_estimated = "~$41-43 per month"
    daily_estimated = "~$1.35-1.45 per day"
  }
}

# Next Steps
output "next_steps" {
  description = "Next steps for deployment"
  value = {
    "1_build_images" = "Build and push Docker images to ECR"
    "2_update_task_definitions" = "Update ECS task definitions with real image URIs"
    "3_run_migrations" = "Run database migrations"
    "4_test_deployment" = "Test the deployed services"
    "5_cleanup" = "Run 'terraform destroy' to clean up resources"
  }
}