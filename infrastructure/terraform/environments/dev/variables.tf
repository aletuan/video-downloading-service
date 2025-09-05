# Development Environment Variables

# Global Configuration
variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "youtube-downloader"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

# Networking Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_count" {
  description = "Number of public subnets"
  type        = number
  default     = 2
}

# Storage Configuration
variable "storage_enable_versioning" {
  description = "Enable S3 bucket versioning"
  type        = bool
  default     = false  # Disabled for dev cost optimization
}

variable "storage_enable_lifecycle_management" {
  description = "Enable S3 lifecycle management"
  type        = bool
  default     = true   # Enabled to optimize costs
}

variable "storage_enable_access_logging" {
  description = "Enable S3 access logging"
  type        = bool
  default     = false  # Disabled for dev
}

variable "storage_enable_cors" {
  description = "Enable CORS for S3 bucket"
  type        = bool
  default     = false  # Disabled for dev
}

variable "storage_enable_cloudfront" {
  description = "Enable CloudFront CDN"
  type        = bool
  default     = false  # Disabled for dev cost optimization
}

variable "storage_cloudfront_price_class" {
  description = "CloudFront price class"
  type        = string
  default     = "PriceClass_100"
}

variable "storage_cors_allowed_origins" {
  description = "CORS allowed origins"
  type        = list(string)
  default     = ["*"]
}

# Database Configuration
variable "postgres_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "15.4"
}

variable "postgres_instance_class" {
  description = "PostgreSQL instance class"
  type        = string
  default     = "db.t3.micro"  # Cost optimized for development
}

variable "postgres_allocated_storage" {
  description = "PostgreSQL allocated storage in GB"
  type        = number
  default     = 20  # Minimum for gp2
}

variable "postgres_max_allocated_storage" {
  description = "PostgreSQL maximum allocated storage in GB"
  type        = number
  default     = 100
}

variable "database_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "youtube_service"
}

variable "database_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "dbadmin"
}

variable "postgres_multi_az_enabled" {
  description = "Enable PostgreSQL Multi-AZ"
  type        = bool
  default     = false  # Disabled for dev cost optimization
}

variable "postgres_backup_retention_days" {
  description = "PostgreSQL backup retention days"
  type        = number
  default     = 7  # Minimum for automated backups
}

variable "postgres_skip_final_snapshot" {
  description = "Skip final snapshot on PostgreSQL deletion"
  type        = bool
  default     = true  # Skip for dev to avoid snapshot costs
}

variable "postgres_deletion_protection" {
  description = "Enable PostgreSQL deletion protection"
  type        = bool
  default     = false  # Disabled for dev to allow easy cleanup
}

variable "postgres_performance_insights_enabled" {
  description = "Enable PostgreSQL Performance Insights"
  type        = bool
  default     = true  # Free for db.t3.micro
}

variable "postgres_monitoring_interval" {
  description = "PostgreSQL enhanced monitoring interval"
  type        = number
  default     = 0  # Disabled for dev cost optimization
}

# Redis Configuration
variable "redis_node_type" {
  description = "Redis node type"
  type        = string
  default     = "cache.t3.micro"  # Cost optimized for development
}

# Container Images
variable "app_image" {
  description = "FastAPI application Docker image"
  type        = string
  default     = "nginx:latest"  # Placeholder - will be replaced with actual image
}

variable "worker_image" {
  description = "Celery worker Docker image"
  type        = string
  default     = "nginx:latest"  # Placeholder - will be replaced with actual image
}

# ECS Configuration
variable "app_cpu" {
  description = "FastAPI app CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 256  # 0.25 vCPU for development
}

variable "app_memory" {
  description = "FastAPI app memory in MB"
  type        = number
  default     = 512  # 0.5 GB for development
}

variable "app_desired_count" {
  description = "Number of FastAPI app tasks"
  type        = number
  default     = 1  # Single instance for development
}

variable "worker_cpu" {
  description = "Celery worker CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 256  # 0.25 vCPU for development
}

variable "worker_memory" {
  description = "Celery worker memory in MB"
  type        = number
  default     = 512  # 0.5 GB for development
}

variable "worker_desired_count" {
  description = "Number of Celery worker tasks"
  type        = number
  default     = 1  # Single worker for development
}

# Monitoring Configuration
variable "container_insights_enabled" {
  description = "Enable CloudWatch Container Insights"
  type        = bool
  default     = false  # Disabled for dev cost optimization
}

variable "log_retention_days" {
  description = "CloudWatch log retention days"
  type        = number
  default     = 7  # Short retention for development
}

# Queue Configuration
variable "queue_depth_alarm_threshold" {
  description = "Threshold for SQS queue depth alarm"
  type        = number
  default     = 100  # Alert when queue has 100+ messages
}

variable "queue_enable_sns_notifications" {
  description = "Enable SNS notifications for queue alarms"
  type        = bool
  default     = false  # Disabled for dev cost optimization
}