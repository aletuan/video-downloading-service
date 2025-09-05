# Compute Module Outputs

# ECS Cluster
output "cluster_id" {
  description = "ECS cluster ID"
  value       = aws_ecs_cluster.main.id
}

output "cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

# FastAPI Application
output "app_service_name" {
  description = "FastAPI ECS service name"
  value       = aws_ecs_service.app.name
}

output "app_service_arn" {
  description = "FastAPI ECS service ARN"
  value       = aws_ecs_service.app.id
}

output "app_task_definition_arn" {
  description = "FastAPI task definition ARN"
  value       = aws_ecs_task_definition.app.arn
}

output "app_task_definition_family" {
  description = "FastAPI task definition family"
  value       = aws_ecs_task_definition.app.family
}

# Celery Worker
output "worker_service_name" {
  description = "Celery worker ECS service name"
  value       = aws_ecs_service.worker.name
}

output "worker_service_arn" {
  description = "Celery worker ECS service ARN"
  value       = aws_ecs_service.worker.id
}

output "worker_task_definition_arn" {
  description = "Celery worker task definition ARN"
  value       = aws_ecs_task_definition.worker.arn
}

output "worker_task_definition_family" {
  description = "Celery worker task definition family"
  value       = aws_ecs_task_definition.worker.family
}

# IAM Roles
output "task_execution_role_arn" {
  description = "ECS task execution role ARN"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "task_role_arn" {
  description = "ECS task role ARN"
  value       = aws_iam_role.ecs_task.arn
}

output "ecs_task_role_arn" {
  description = "ECS task role ARN (alias for compatibility)"
  value       = aws_iam_role.ecs_task.arn
}

# CloudWatch Log Groups
output "app_log_group_name" {
  description = "CloudWatch log group name for FastAPI application"
  value       = aws_cloudwatch_log_group.app.name
}

output "worker_log_group_name" {
  description = "CloudWatch log group name for Celery worker"
  value       = aws_cloudwatch_log_group.worker.name
}