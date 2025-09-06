# Database Module Outputs

# PostgreSQL Outputs
output "postgres_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "postgres_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.postgres.port
}

output "postgres_database_name" {
  description = "RDS PostgreSQL database name"
  value       = aws_db_instance.postgres.db_name
}

output "postgres_username" {
  description = "RDS PostgreSQL master username"
  value       = aws_db_instance.postgres.username
  sensitive   = true
}

output "postgres_password" {
  description = "RDS PostgreSQL master password"
  value       = random_password.db_password.result
  sensitive   = true
}

output "postgres_identifier" {
  description = "RDS PostgreSQL identifier"
  value       = aws_db_instance.postgres.identifier
}

output "postgres_arn" {
  description = "RDS PostgreSQL ARN"
  value       = aws_db_instance.postgres.arn
}

# Redis Outputs
output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "redis_port" {
  description = "ElastiCache Redis port"
  value       = aws_elasticache_cluster.redis.port
}

output "redis_cluster_id" {
  description = "ElastiCache Redis cluster ID"
  value       = aws_elasticache_cluster.redis.cluster_id
}

# Connection Strings (for application configuration)
output "postgres_connection_string" {
  description = "PostgreSQL connection string for application"
  value       = "postgresql://${aws_db_instance.postgres.username}:${random_password.db_password.result}@${aws_db_instance.postgres.endpoint}/${aws_db_instance.postgres.db_name}"
  sensitive   = true
}

output "redis_connection_string" {
  description = "Redis connection string for application"
  value       = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:${aws_elasticache_cluster.redis.port}/0"
}

# Parameter Store Parameters
output "db_password_parameter" {
  description = "Systems Manager parameter name for database password"
  value       = aws_ssm_parameter.db_password.name
}

output "db_host_parameter" {
  description = "Systems Manager parameter name for database host"
  value       = aws_ssm_parameter.db_host.name
}

output "redis_host_parameter" {
  description = "Systems Manager parameter name for Redis host"
  value       = aws_ssm_parameter.redis_host.name
}