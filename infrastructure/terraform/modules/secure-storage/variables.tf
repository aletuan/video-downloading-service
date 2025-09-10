# Variables for Secure Storage Module

variable "project_name" {
  description = "Name of the project"
  type        = string
  validation {
    condition     = length(var.project_name) > 0 && length(var.project_name) <= 32
    error_message = "Project name must be between 1 and 32 characters."
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "ecs_task_role_arn" {
  description = "ARN of the ECS task role that needs access to the secure config bucket"
  type        = string
  validation {
    condition     = can(regex("^arn:aws:iam::\\d{12}:role/.*", var.ecs_task_role_arn))
    error_message = "ECS task role ARN must be a valid IAM role ARN."
  }
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "enable_encryption" {
  description = "Enable server-side encryption for S3 buckets"
  type        = bool
  default     = true
}

variable "enable_versioning" {
  description = "Enable versioning for the secure config bucket"
  type        = bool
  default     = true
}

variable "enable_access_logging" {
  description = "Enable access logging for the secure config bucket"
  type        = bool
  default     = true
}

variable "cookie_retention_days" {
  description = "Number of days to retain cookie files"
  type        = number
  default     = 90
  validation {
    condition     = var.cookie_retention_days > 0 && var.cookie_retention_days <= 365
    error_message = "Cookie retention days must be between 1 and 365."
  }
}

variable "version_retention_days" {
  description = "Number of days to retain non-current versions"
  type        = number
  default     = 30
  validation {
    condition     = var.version_retention_days > 0 && var.version_retention_days <= 90
    error_message = "Version retention days must be between 1 and 90."
  }
}

variable "log_retention_days" {
  description = "Number of days to retain access logs"
  type        = number
  default     = 365
  validation {
    condition     = var.log_retention_days > 0 && var.log_retention_days <= 730
    error_message = "Log retention days must be between 1 and 730."
  }
}

variable "enable_security_monitoring" {
  description = "Enable security monitoring and alerting"
  type        = bool
  default     = true
}

variable "alert_email" {
  description = "Email address for security alerts (optional)"
  type        = string
  default     = ""
  validation {
    condition     = var.alert_email == "" || can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", var.alert_email))
    error_message = "Alert email must be a valid email address or empty string."
  }
}

variable "enable_cloudwatch_logging" {
  description = "Enable CloudWatch logging for S3 access events"
  type        = bool
  default     = true
}