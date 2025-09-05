# Development Environment Configuration
# Created for Phase 6A AWS deployment

# Global Configuration
project_name = "youtube-downloader"
environment  = "dev"
aws_region   = "us-east-1"

# Networking Configuration
vpc_cidr             = "10.0.0.0/16"
public_subnet_count  = 2

# Storage Configuration (Development Optimized)
storage_enable_versioning          = false  # Cost optimization
storage_enable_lifecycle_management = true   # Cost optimization
storage_enable_access_logging      = false  # Cost optimization
storage_enable_cors                = false  # Not needed for dev
storage_enable_cloudfront          = false  # Cost optimization
storage_cloudfront_price_class     = "PriceClass_100"
storage_cors_allowed_origins       = ["*"]

# Database Configuration (Development Optimized)
postgres_version                   = "15.8"
postgres_instance_class           = "db.t3.micro"      # ~$12/month
postgres_allocated_storage        = 20                 # Minimum for gp2
postgres_max_allocated_storage    = 100
database_name                     = "youtube_service"
database_username                 = "dbadmin"
postgres_multi_az_enabled         = false             # Cost optimization
postgres_backup_retention_days    = 7                 # Minimum
postgres_skip_final_snapshot      = true              # Cost optimization
postgres_deletion_protection      = false             # Allow easy cleanup
postgres_performance_insights_enabled = true          # Free for t3.micro
postgres_monitoring_interval      = 0                 # Cost optimization

# Redis Configuration (Development Optimized)
redis_node_type = "cache.t3.micro"  # ~$11/month

# Container Images (Updated with real ECR URIs)
app_image    = "575108929177.dkr.ecr.us-east-1.amazonaws.com/youtube-downloader/app:latest"
worker_image = "575108929177.dkr.ecr.us-east-1.amazonaws.com/youtube-downloader/worker:latest"

# ECS Configuration (Development Optimized)
app_cpu             = 256  # 0.25 vCPU
app_memory          = 512  # 0.5 GB RAM
app_desired_count   = 1    # Single instance

worker_cpu          = 256  # 0.25 vCPU
worker_memory       = 512  # 0.5 GB RAM
worker_desired_count = 1   # Single worker

# Monitoring Configuration (Development Optimized)
container_insights_enabled = false  # Cost optimization
log_retention_days         = 7      # Short retention for dev

# Queue Configuration (Development Optimized)
queue_depth_alarm_threshold    = 100    # Alert when queue has 100+ messages
queue_enable_sns_notifications = false  # Cost optimization

# Expected Monthly Cost: ~$40-43
# Expected Daily Cost: ~$1.35-1.45