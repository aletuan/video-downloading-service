# Database Module Variables

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
  description = "List of subnet IDs for database deployment"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group ID for RDS"
  type        = string
}

variable "redis_security_group_id" {
  description = "Security group ID for Redis"
  type        = string
}

# PostgreSQL Configuration
variable "postgres_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15.12"
}

variable "postgres_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"  # ~$12/month
}

variable "postgres_allocated_storage" {
  description = "Initial storage size in GB"
  type        = number
  default     = 20
}

variable "postgres_max_allocated_storage" {
  description = "Maximum storage size for auto-scaling in GB"
  type        = number
  default     = 100
}

variable "database_name" {
  description = "Name of the initial database"
  type        = string
  default     = "youtube_service"
}

variable "database_username" {
  description = "Master username for the database"
  type        = string
  default     = "dbadmin"
}

variable "multi_az_enabled" {
  description = "Enable Multi-AZ deployment for high availability"
  type        = bool
  default     = false  # Disabled for development cost optimization
}

variable "backup_retention_days" {
  description = "Number of days to retain backups"
  type        = number
  default     = 7
}

variable "skip_final_snapshot" {
  description = "Skip final snapshot when destroying (set to false for production)"
  type        = bool
  default     = true  # Skip for development to avoid snapshot costs
}

variable "deletion_protection" {
  description = "Enable deletion protection"
  type        = bool
  default     = false  # Disabled for development to allow easy cleanup
}

variable "performance_insights_enabled" {
  description = "Enable Performance Insights (free for db.t3.micro)"
  type        = bool
  default     = true
}

variable "monitoring_interval" {
  description = "Enhanced monitoring interval in seconds (0, 1, 5, 10, 15, 30, 60)"
  type        = number
  default     = 0  # Disabled for development cost optimization
}

# Redis Configuration
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"  # ~$11/month
}