# Database Module - RDS PostgreSQL and ElastiCache Redis
# Optimized for development environment with cost-effective configurations

# Random password for RDS
resource "random_password" "db_password" {
  length  = 16
  special = true
}

# Random suffix for unique resource names
resource "random_id" "db_suffix" {
  byte_length = 4
}

# DB Subnet Group for RDS
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}-db-subnet-group-${random_id.db_suffix.hex}"
  subnet_ids = var.subnet_ids

  tags = {
    Name = "${var.project_name}-${var.environment}-db-subnet-group"
  }
}

# RDS PostgreSQL Instance
resource "aws_db_instance" "postgres" {
  # Basic Configuration
  identifier = "${var.project_name}-${var.environment}-postgres-${random_id.db_suffix.hex}"
  
  # Engine Configuration
  engine              = "postgres"
  engine_version      = var.postgres_version
  instance_class      = var.postgres_instance_class
  
  # Storage Configuration
  allocated_storage     = var.postgres_allocated_storage
  max_allocated_storage = var.postgres_max_allocated_storage
  storage_type         = "gp2"
  storage_encrypted    = true
  
  # Database Configuration
  db_name  = var.database_name
  username = var.database_username
  password = random_password.db_password.result
  
  # Network Configuration
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.security_group_id]
  publicly_accessible    = false
  port                   = 5432
  
  # High Availability (disabled for dev cost optimization)
  multi_az = var.multi_az_enabled
  
  # Backup Configuration
  backup_retention_period = var.backup_retention_days
  backup_window          = "03:00-04:00"  # UTC
  maintenance_window     = "sun:04:00-sun:05:00"  # UTC
  
  # Development optimizations
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.project_name}-${var.environment}-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"
  deletion_protection       = var.deletion_protection
  
  # Performance Insights (free tier)
  performance_insights_enabled = var.performance_insights_enabled
  
  # Monitoring
  monitoring_interval = var.monitoring_interval
  monitoring_role_arn = var.monitoring_interval > 0 ? aws_iam_role.rds_monitoring[0].arn : null
  
  # Enable automated minor version upgrades
  auto_minor_version_upgrade = true
  
  # Parameter group
  parameter_group_name = aws_db_parameter_group.postgres.name
  
  tags = {
    Name = "${var.project_name}-${var.environment}-postgres"
  }
}

# Custom Parameter Group for PostgreSQL
resource "aws_db_parameter_group" "postgres" {
  family = "postgres15"
  name   = "${var.project_name}-${var.environment}-postgres-params-${random_id.db_suffix.hex}"

  # Optimize for development workload
  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }
  
  parameter {
    name  = "log_statement"
    value = "mod"  # Log modifications for debugging
  }
  
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"  # Log queries taking longer than 1 second
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-postgres-params"
  }
}

# IAM Role for RDS Enhanced Monitoring (only if monitoring enabled)
resource "aws_iam_role" "rds_monitoring" {
  count = var.monitoring_interval > 0 ? 1 : 0
  
  name = "${var.project_name}-${var.environment}-rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-${var.environment}-rds-monitoring-role"
  }
}

# Attach the RDS Enhanced Monitoring policy
resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  count = var.monitoring_interval > 0 ? 1 : 0
  
  role       = aws_iam_role.rds_monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# ElastiCache Subnet Group
resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.project_name}-${var.environment}-redis-subnet-group"
  subnet_ids = var.subnet_ids

  tags = {
    Name = "${var.project_name}-${var.environment}-redis-subnet-group"
  }
}

# ElastiCache Redis Cluster
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${var.project_name}-${var.environment}-redis"
  engine               = "redis"
  node_type           = var.redis_node_type
  num_cache_nodes     = 1
  parameter_group_name = "default.redis7"
  port                = 6379
  
  # Network Configuration
  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [var.redis_security_group_id]
  
  # Development optimizations
  apply_immediately = true
  
  # Maintenance
  maintenance_window = "sun:05:00-sun:06:00"  # UTC
  
  tags = {
    Name = "${var.project_name}-${var.environment}-redis"
  }
}

# Store database credentials in AWS Systems Manager Parameter Store
resource "aws_ssm_parameter" "db_password" {
  name        = "/${var.project_name}/${var.environment}/database/password"
  description = "RDS PostgreSQL password"
  type        = "SecureString"
  value       = random_password.db_password.result

  tags = {
    Name = "${var.project_name}-${var.environment}-db-password"
  }
}

resource "aws_ssm_parameter" "db_host" {
  name        = "/${var.project_name}/${var.environment}/database/host"
  description = "RDS PostgreSQL endpoint"
  type        = "String"
  value       = aws_db_instance.postgres.endpoint

  tags = {
    Name = "${var.project_name}-${var.environment}-db-host"
  }
}

resource "aws_ssm_parameter" "redis_host" {
  name        = "/${var.project_name}/${var.environment}/redis/host"
  description = "ElastiCache Redis endpoint"
  type        = "String"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address

  tags = {
    Name = "${var.project_name}-${var.environment}-redis-host"
  }
}