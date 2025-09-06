# Terraform Backend Configuration
# This file configures remote state storage in S3 with DynamoDB locking

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

  # Uncomment and configure after creating S3 bucket for state
  # backend "s3" {
  #   bucket         = "youtube-downloader-terraform-state"
  #   key            = "environments/dev/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "youtube-downloader-terraform-locks"
  #   encrypt        = true
  # }
}

# AWS Provider Configuration
provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = "youtube-downloader"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Random provider for generating unique names
provider "random" {}

# Variables
variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}