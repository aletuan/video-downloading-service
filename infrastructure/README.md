# Infrastructure

This directory contains Terraform infrastructure code for the YouTube Video Download Service.

## Directory Structure

```
infrastructure/
├── terraform/
│   ├── environments/
│   │   └── dev/                    # Development environment
│   │       ├── main.tf             # Main configuration
│   │       ├── variables.tf        # Variable definitions
│   │       ├── outputs.tf          # Output definitions
│   │       └── terraform.tfvars.example  # Example configuration
│   ├── modules/
│   │   ├── networking/            # VPC, subnets, security groups
│   │   ├── database/              # RDS PostgreSQL, ElastiCache Redis
│   │   ├── compute/               # ECS Fargate, task definitions
│   │   └── storage/               # S3 bucket, CloudFront (optional)
│   └── shared/
│       └── backend.tf             # Terraform backend configuration
└── README.md                      # This file
```

## Quick Start

### Prerequisites

1. **AWS CLI configured** with appropriate credentials
2. **Terraform installed** (>= 1.0)
3. **Docker** for building container images

### Development Deployment

1. **Navigate to development environment:**
   ```bash
   cd infrastructure/terraform/environments/dev
   ```

2. **Create terraform.tfvars file:**
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your preferences
   ```

3. **Initialize Terraform:**
   ```bash
   terraform init
   ```

4. **Plan the deployment:**
   ```bash
   terraform plan
   ```

5. **Apply the infrastructure:**
   ```bash
   terraform apply
   ```

6. **View outputs:**
   ```bash
   terraform output
   ```

### Cleanup

To remove all resources and stop incurring costs:

```bash
terraform destroy
```

## Cost Information

### Development Environment (~$40-43/month)
- **ECS Fargate**: ~$14/month (2 tasks × 0.25 vCPU × 0.5GB)
- **RDS PostgreSQL**: ~$12/month (db.t3.micro, single-AZ)
- **ElastiCache Redis**: ~$11/month (cache.t3.micro)
- **VPC Networking**: ~$2/month (no NAT Gateway)
- **S3 Storage**: ~$1-2/month (50GB standard)
- **CloudWatch Logs**: ~$1/month (7-day retention)

**Daily cost: ~$1.35-1.45**

## Architecture Overview

The infrastructure deploys:

1. **VPC with public subnets** (no NAT Gateway for cost optimization)
2. **ECS Fargate cluster** with FastAPI app and Celery worker
3. **RDS PostgreSQL** (db.t3.micro) for application data
4. **ElastiCache Redis** (cache.t3.micro) for caching and job queue
5. **S3 bucket** for video file storage
6. **Security groups** with least-privilege access
7. **CloudWatch logs** for application monitoring

## Configuration

### Key Variables

Edit `terraform.tfvars` to customize:

```hcl
# Instance sizing
postgres_instance_class = "db.t3.micro"  # or db.t3.small for more performance
redis_node_type        = "cache.t3.micro"  # or cache.t3.small

# Container resources
app_cpu    = 256  # 0.25 vCPU (can increase to 512, 1024, etc.)
app_memory = 512  # 0.5 GB RAM

# Feature toggles
storage_enable_cloudfront = false  # Enable for production
postgres_multi_az_enabled = false  # Enable for production
```

### Environment Scaling

To scale up for higher loads:

1. **Increase container resources:**
   ```hcl
   app_cpu    = 512   # 0.5 vCPU
   app_memory = 1024  # 1 GB RAM
   app_desired_count = 2  # Multiple instances
   ```

2. **Upgrade database:**
   ```hcl
   postgres_instance_class = "db.t3.small"  # More CPU/memory
   ```

3. **Enable production features:**
   ```hcl
   postgres_multi_az_enabled = true   # High availability
   storage_enable_cloudfront = true   # Global CDN
   ```

## Module Documentation

### Networking Module
- Creates VPC with public subnets across 2 AZs
- Security groups for ECS, RDS, Redis with least-privilege rules
- No NAT Gateway (cost optimization for development)

### Database Module
- RDS PostgreSQL with encryption at rest
- ElastiCache Redis cluster
- Automated backups and maintenance windows
- Systems Manager parameters for connection strings

### Compute Module
- ECS Fargate cluster for serverless containers
- Task definitions for FastAPI app and Celery worker
- IAM roles for S3 access and Systems Manager
- CloudWatch log groups for application logs

### Storage Module
- S3 bucket with encryption and lifecycle policies
- Optional CloudFront CDN (disabled for dev)
- CORS configuration for direct uploads (optional)

## Troubleshooting

### Common Issues

1. **Terraform init fails:**
   ```bash
   # Clear cache and re-initialize
   rm -rf .terraform
   terraform init
   ```

2. **Resource creation timeouts:**
   - RDS instances can take 5-15 minutes to create
   - Check AWS CloudFormation console for detailed errors

3. **ECS tasks not starting:**
   - Check CloudWatch logs: `/ecs/youtube-downloader-dev-app`
   - Verify container images exist and are accessible

4. **High costs:**
   - Run `terraform destroy` to clean up all resources
   - Check AWS Billing dashboard for unexpected charges

### Getting Help

- **Infrastructure issues**: Check `docs/AWS-INFRASTRUCTURE.md`
- **Application deployment**: Check main project README
- **Terraform docs**: https://registry.terraform.io/providers/hashicorp/aws/latest/docs

## Security Notes

- All databases are in private subnets (or public with security groups)
- Secrets stored in Systems Manager Parameter Store
- IAM roles follow least-privilege principles
- S3 buckets have public access blocked by default
- All resources encrypted at rest where possible

## Next Steps

1. **Build Docker images** and push to ECR
2. **Update task definitions** with real image URIs
3. **Run database migrations** 
4. **Test the deployment** thoroughly
5. **Set up CI/CD pipeline** for automated deployments