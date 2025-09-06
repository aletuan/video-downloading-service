# Variables for Queue Module

variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

variable "ecs_task_role_arn" {
  description = "ARN of the ECS task role for queue access"
  type        = string
}

variable "queue_depth_alarm_threshold" {
  description = "Threshold for queue depth alarm"
  type        = number
  default     = 100
}

variable "enable_sns_notifications" {
  description = "Enable SNS notifications for queue alarms"
  type        = bool
  default     = false
}