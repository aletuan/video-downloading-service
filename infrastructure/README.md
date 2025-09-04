# Infrastructure Directory

This directory contains Infrastructure as Code (IaC) configurations for deploying the YouTube Download Service to AWS.

## Structure

- `modules/` - Terraform modules for different AWS resources
- `environments/` - Environment-specific configurations
- `main.tf` - Main Terraform configuration
- `variables.tf` - Input variables
- `outputs.tf` - Output values

## Terraform Modules

- `vpc/` - VPC and networking resources
- `ecs/` - ECS cluster and service configuration
- `rds/` - RDS database configuration
- `elasticache/` - ElastiCache Redis configuration
- `s3/` - S3 bucket and CloudFront distribution
- `iam/` - IAM roles and policies

## Usage

1. Initialize Terraform:
   ```bash
   cd infrastructure
   terraform init
   ```

2. Plan deployment:
   ```bash
   terraform plan
   ```

3. Apply changes:
   ```bash
   terraform apply
   ```