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
  value       = "postgresql://${module.database.postgres_username}:${module.database.postgres_password}@${module.database.postgres_endpoint}/${module.database.postgres_database_name}"

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
}