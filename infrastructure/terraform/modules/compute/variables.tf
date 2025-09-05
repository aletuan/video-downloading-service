# Compute Module Variables

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "youtube-downloader"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for ECS deployment"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "s3_bucket_arn" {
  description = "ARN of the S3 bucket for video storage"
  type        = string
}

variable "database_url_parameter" {
  description = "Systems Manager parameter name for database URL"
  type        = string
}

variable "redis_url_parameter" {
  description = "Systems Manager parameter name for Redis URL"
  type        = string
}

# Container Images
variable "app_image" {
  description = "Docker image for FastAPI application"
  type        = string
  default     = "youtube-downloader/app:latest"
}

variable "worker_image" {
  description = "Docker image for Celery worker"
  type        = string
  default     = "youtube-downloader/worker:latest"
}

# FastAPI Application Configuration
variable "app_cpu" {
  description = "CPU units for FastAPI application (256 = 0.25 vCPU)"
  type        = number
  default     = 256  # 0.25 vCPU for development
}

variable "app_memory" {
  description = "Memory in MB for FastAPI application"
  type        = number
  default     = 512  # 0.5 GB for development
}

variable "app_desired_count" {
  description = "Desired number of FastAPI tasks"
  type        = number
  default     = 1  # Single instance for development
}

# Celery Worker Configuration
variable "worker_cpu" {
  description = "CPU units for Celery worker (256 = 0.25 vCPU)"
  type        = number
  default     = 256  # 0.25 vCPU for development
}

variable "worker_memory" {
  description = "Memory in MB for Celery worker"
  type        = number
  default     = 512  # 0.5 GB for development
}

variable "worker_desired_count" {
  description = "Desired number of Celery worker tasks"
  type        = number
  default     = 1  # Single worker for development
}

# Monitoring and Logging
variable "container_insights_enabled" {
  description = "Enable CloudWatch Container Insights"
  type        = bool
  default     = false  # Disabled for development cost optimization
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7  # Short retention for development
}