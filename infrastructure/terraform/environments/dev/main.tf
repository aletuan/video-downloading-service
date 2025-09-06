# Development Environment Configuration
# Optimal development setup with cost optimization

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }

  # Backend configuration - uncomment after creating S3 bucket
  # backend "s3" {
  #   bucket         = "youtube-downloader-terraform-state"
  #   key            = "environments/dev/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "youtube-downloader-terraform-locks"
  #   encrypt        = true
  # }
}

# AWS Provider
provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      CostCenter  = "development"
    }
  }
}

provider "random" {}

# Local variables
locals {
  environment = "dev"
  common_tags = {
    Project     = var.project_name
    Environment = local.environment
    ManagedBy   = "terraform"
    CostCenter  = "development"
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Networking Module
module "networking" {
  source = "../../modules/networking"

  project_name         = var.project_name
  environment          = local.environment
  vpc_cidr            = var.vpc_cidr
  public_subnet_count = var.public_subnet_count
}

# Storage Module
module "storage" {
  source = "../../modules/storage"

  project_name                = var.project_name
  environment                 = local.environment
  enable_versioning          = var.storage_enable_versioning
  enable_lifecycle_management = var.storage_enable_lifecycle_management
  enable_access_logging      = var.storage_enable_access_logging
  enable_cors                = var.storage_enable_cors
  enable_cloudfront          = var.storage_enable_cloudfront
  cloudfront_price_class     = var.storage_cloudfront_price_class
  cors_allowed_origins       = var.storage_cors_allowed_origins
}

# Database Module
module "database" {
  source = "../../modules/database"

  project_name                    = var.project_name
  environment                     = local.environment
  subnet_ids                      = module.networking.public_subnet_ids
  security_group_id               = module.networking.rds_security_group_id
  redis_security_group_id         = module.networking.redis_security_group_id
  
  # PostgreSQL Configuration
  postgres_version                = var.postgres_version
  postgres_instance_class         = var.postgres_instance_class
  postgres_allocated_storage      = var.postgres_allocated_storage
  postgres_max_allocated_storage  = var.postgres_max_allocated_storage
  database_name                   = var.database_name
  database_username               = var.database_username
  multi_az_enabled               = var.postgres_multi_az_enabled
  backup_retention_days          = var.postgres_backup_retention_days
  skip_final_snapshot            = var.postgres_skip_final_snapshot
  deletion_protection            = var.postgres_deletion_protection
  performance_insights_enabled   = var.postgres_performance_insights_enabled
  monitoring_interval            = var.postgres_monitoring_interval
  
  # Redis Configuration
  redis_node_type = var.redis_node_type
}

# Create Systems Manager parameters for application configuration
resource "aws_ssm_parameter" "database_url" {
  name        = "/${var.project_name}/${local.environment}/database/url"
  description = "Database connection URL for application"
  type        = "SecureString"
  value       = "postgresql+asyncpg://${module.database.postgres_username}:${module.database.postgres_password}@${module.database.postgres_endpoint}/${module.database.postgres_database_name}?ssl=require"

  tags = local.common_tags
}

resource "aws_ssm_parameter" "redis_url" {
  name        = "/${var.project_name}/${local.environment}/redis/url"
  description = "Redis connection URL for application"
  type        = "String"
  value       = "redis://${module.database.redis_endpoint}:${module.database.redis_port}/0"

  tags = local.common_tags
}

# Compute Module
module "compute" {
  source = "../../modules/compute"

  project_name            = var.project_name
  environment             = local.environment
  subnet_ids              = module.networking.public_subnet_ids
  security_group_id       = module.networking.ecs_security_group_id
  s3_bucket_arn          = module.storage.s3_bucket_arn
  database_url_parameter  = aws_ssm_parameter.database_url.name
  redis_url_parameter     = aws_ssm_parameter.redis_url.name
  
  # Container Images (will need to be built and pushed to ECR)
  app_image    = var.app_image
  worker_image = var.worker_image
  
  # Resource Configuration
  app_cpu             = var.app_cpu
  app_memory          = var.app_memory
  app_desired_count   = var.app_desired_count
  worker_cpu          = var.worker_cpu
  worker_memory       = var.worker_memory
  worker_desired_count = var.worker_desired_count
  
  # Monitoring
  container_insights_enabled = var.container_insights_enabled
  log_retention_days         = var.log_retention_days
  
  # Load Balancer Integration
  target_group_arn = module.load_balancer.target_group_arn
}

# Queue Module - Deployed after compute module for ECS task role dependency
module "queue" {
  source = "../../modules/queue"

  project_name               = var.project_name
  environment               = local.environment
  ecs_task_role_arn         = module.compute.ecs_task_role_arn
  queue_depth_alarm_threshold = var.queue_depth_alarm_threshold
  enable_sns_notifications  = var.queue_enable_sns_notifications
}

# Load Balancer Module - Deployed after networking and compute modules
module "load_balancer" {
  source = "../../modules/load_balancer"

  project_name     = var.project_name
  environment     = local.environment
  vpc_id          = module.networking.vpc_id
  subnet_ids      = module.networking.public_subnet_ids
  security_group_id = module.networking.alb_security_group_id

  # Health check configuration
  health_check_path     = "/health"
  health_check_interval = 30
  health_check_timeout  = 5
  healthy_threshold     = 2
  unhealthy_threshold   = 3

  # ALB configuration  
  enable_deletion_protection = false  # Development environment
  enable_http2              = true
  idle_timeout              = 60

  # Target group configuration
  target_group_port     = 8000
  target_group_protocol = "HTTP"

  # SSL certificate (optional - can be added later)
  certificate_arn = ""  # No SSL for development initially

  tags = local.common_tags
}

# Database Migration - Run after compute module is deployed
resource "null_resource" "database_migration" {
  depends_on = [
    module.compute,
    module.database,
    aws_ssm_parameter.database_url
  ]

  triggers = {
    # Re-run if database endpoint changes or compute module changes
    database_endpoint = module.database.postgres_endpoint
    cluster_name     = module.compute.cluster_name
    always_run       = timestamp()
  }

  provisioner "local-exec" {
    command = <<-EOF
      set -e
      
      echo "Starting database migration via ECS task..."
      
      # Get cluster name and task definition
      CLUSTER_NAME="${module.compute.cluster_name}"
      
      # Get the latest task definition ARN
      TASK_DEF_ARN=$(aws ecs describe-task-definition \
        --task-definition "${var.project_name}-${local.environment}-app" \
        --query 'taskDefinition.taskDefinitionArn' \
        --output text)
      
      if [[ -z "$TASK_DEF_ARN" || "$TASK_DEF_ARN" == "None" ]]; then
        echo "Error: Could not find task definition"
        exit 1
      fi
      
      echo "Using task definition: $TASK_DEF_ARN"
      
      # Get subnet IDs for network configuration
      SUBNET_IDS='${jsonencode(module.networking.public_subnet_ids)}'
      SUBNET_LIST=$(echo $SUBNET_IDS | jq -r '.[]' | tr '\n' ',' | sed 's/,$//')
      
      # First attempt: Run Alembic migration
      echo "Attempting Alembic migration..."
      MIGRATION_TASK=$(aws ecs run-task \
        --cluster "$CLUSTER_NAME" \
        --task-definition "$TASK_DEF_ARN" \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_LIST],securityGroups=[${module.networking.ecs_security_group_id}],assignPublicIp=ENABLED}" \
        --overrides '{"containerOverrides":[{"name":"fastapi-app","command":["alembic","upgrade","head"]}]}' \
        --launch-type FARGATE \
        --query 'tasks[0].taskArn' \
        --output text 2>/dev/null || echo "FAILED")
      
      if [[ "$MIGRATION_TASK" != "FAILED" && "$MIGRATION_TASK" != "None" && -n "$MIGRATION_TASK" ]]; then
        echo "Migration task started: $MIGRATION_TASK"
        echo "Waiting for migration to complete..."
        
        # Wait for task to complete (with timeout)
        aws ecs wait tasks-stopped --cluster "$CLUSTER_NAME" --tasks "$MIGRATION_TASK" --cli-read-timeout 300 || echo "Migration task timeout or failed"
        
        # Check exit code
        EXIT_CODE=$(aws ecs describe-tasks \
          --cluster "$CLUSTER_NAME" \
          --tasks "$MIGRATION_TASK" \
          --query 'tasks[0].containers[0].exitCode' \
          --output text 2>/dev/null || echo "1")
        
        if [[ "$EXIT_CODE" == "0" ]]; then
          echo "✅ Alembic migration completed successfully"
          exit 0
        else
          echo "⚠️  Alembic migration failed, trying direct table creation..."
        fi
      else
        echo "⚠️  Could not start Alembic migration task, trying direct table creation..."
      fi
      
      # Fallback: Direct table creation using Python script
      echo "Creating tables directly using asyncpg..."
      
      # Create Python script for table creation
      PYTHON_SCRIPT='
import os
import asyncio
import asyncpg
import sys

async def create_tables():
    try:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("Error: DATABASE_URL environment variable not found")
            sys.exit(1)
            
        print(f"Connecting to database...")
        conn = await asyncpg.connect(database_url)
        
        # Create api_keys table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                key VARCHAR(255) UNIQUE NOT NULL,
                permission_level VARCHAR(50) NOT NULL,
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP WITH TIME ZONE,
                usage_count INTEGER DEFAULT 0,
                created_by VARCHAR(255)
            );
        """)
        print("✅ api_keys table created/verified")
        
        # Create download_jobs table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS download_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                url VARCHAR(2048) NOT NULL,
                status VARCHAR(50) DEFAULT 'queued',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP WITH TIME ZONE,
                quality VARCHAR(50),
                output_format VARCHAR(50),
                include_transcription BOOLEAN DEFAULT FALSE,
                subtitle_languages JSON,
                video_info JSON,
                files JSON,
                progress INTEGER DEFAULT 0,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0
            );
        """)
        print("✅ download_jobs table created/verified")
        
        # Create alembic_version table for future migrations
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            );
        """)
        print("✅ alembic_version table created/verified")
        
        await conn.close()
        print("✅ All database tables created successfully")
        
    except Exception as e:
        print(f"❌ Error creating tables: {str(e)}")
        sys.exit(1)

asyncio.run(create_tables())
'
      
      # Run table creation task
      TABLE_TASK=$(aws ecs run-task \
        --cluster "$CLUSTER_NAME" \
        --task-definition "$TASK_DEF_ARN" \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_LIST],securityGroups=[${module.networking.ecs_security_group_id}],assignPublicIp=ENABLED}" \
        --overrides "{\"containerOverrides\":[{\"name\":\"fastapi-app\",\"command\":[\"python\",\"-c\",\"$(echo "$PYTHON_SCRIPT" | sed 's/"/\\"/g')\"]}]}" \
        --launch-type FARGATE \
        --query 'tasks[0].taskArn' \
        --output text 2>/dev/null || echo "FAILED")
      
      if [[ "$TABLE_TASK" != "FAILED" && "$TABLE_TASK" != "None" && -n "$TABLE_TASK" ]]; then
        echo "Table creation task started: $TABLE_TASK"
        echo "Waiting for table creation to complete..."
        
        aws ecs wait tasks-stopped --cluster "$CLUSTER_NAME" --tasks "$TABLE_TASK" --cli-read-timeout 300 || echo "Table creation timeout"
        
        # Check exit code
        EXIT_CODE=$(aws ecs describe-tasks \
          --cluster "$CLUSTER_NAME" \
          --tasks "$TABLE_TASK" \
          --query 'tasks[0].containers[0].exitCode' \
          --output text 2>/dev/null || echo "1")
        
        if [[ "$EXIT_CODE" == "0" ]]; then
          echo "✅ Database tables created successfully via direct method"
        else
          echo "❌ Table creation failed"
          exit 1
        fi
      else
        echo "❌ Could not start table creation task"
        exit 1
      fi
    EOF
  }
}