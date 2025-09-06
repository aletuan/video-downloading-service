# YouTube Video Download Service - AWS Deployment Guide

> **Related Documentation**: See [AWS-INFRASTRUCTURE.md](AWS-INFRASTRUCTURE.md) for comprehensive architecture planning, service configurations, and scaling strategies.

## 📋 Executive Summary

**Current Status**: Phase 6G - Production Deployment **FULLY COMPLETED** ✅  
**Next Phase**: Phase 6H - Extended Production Features (Optional)  
**Infrastructure Cost**: ~$60/month (development environment)  
**Deployment Method**: Terraform + ECS Fargate + Application Load Balancer

### 🎯 **Key Achievements**
- ✅ **Complete AWS Infrastructure**: All 6 phases (A-G) successfully deployed per [AWS-INFRASTRUCTURE.md](AWS-INFRASTRUCTURE.md) "Optimal Development" configuration
- ✅ **Production Application**: FastAPI + Celery services running on ECS Fargate
- ✅ **Bootstrap Security**: Solved "chicken and egg" API key problem for production
- ✅ **Health Monitoring**: Load balancer health checks passing
- ✅ **Cost Optimized**: Development-friendly resource sizing (~$60/month)

### 🚀 **Production Ready Features**
- **Application Endpoint**: Load balancer with health checks
- **Background Processing**: Celery workers with SQS queues
- **Database**: PostgreSQL RDS with Redis caching
- **Storage**: S3 bucket for video/subtitle files
- **Security**: Bootstrap endpoint for initial API key creation
- **Monitoring**: CloudWatch logging and basic alarms

---

## 📊 Phase Completion Status

| Phase | Component | Status | Cost/Month | Key Resources |
|-------|-----------|--------|------------|---------------|
| **6A** | Core Infrastructure | ✅ Complete | $0.00 | VPC, Subnets, Security Groups, Internet Gateway |
| **6B** | Storage Layer | ✅ Complete | ~$0.25-0.50 | S3 Bucket, SSM Parameters |
| **6C** | Database & Cache | ✅ Complete | ~$23.00 | RDS PostgreSQL, ElastiCache Redis |
| **6D** | Queue System | ✅ Complete | ~$0.70 | SQS Queues, CloudWatch Alarms |
| **6E** | Compute Platform | ✅ Complete | ~$15.00 | ECS Cluster, Task Definitions, IAM Roles |
| **6F** | Load Balancing | ✅ Complete | ~$21.00 | Application Load Balancer, Target Groups |
| **6G** | Production Apps | ✅ Deployed* | $0.00 | Container Images, Bootstrap Endpoint |
| **6H** | Extended Features | ⏳ Optional | TBD | SSL, Domain, Enhanced Monitoring |

**Total Monthly Cost**: ~$59.95-60.20 (development environment)

***Phase 6G Note**: Infrastructure deployed and bootstrap endpoint working. Full video download functionality not yet tested end-to-end.*

---

## 🏗️ Infrastructure Architecture Overview

### Resource Relationships
```
┌─ Networking (Phase 6A) ─────────────────────────────────┐
│  VPC → Subnets → Internet Gateway → Security Groups     │
│  └─────────────────┬────────────────────────────────────┘
│                    │
├─ Storage (6B) ─────┼─ Database (6C) ─────┬─ Queues (6D) ─┐
│  S3 Bucket         │  RDS PostgreSQL     │  SQS Queues   │
│  SSM Parameters    │  ElastiCache Redis  │  CloudWatch   │
│                    │  SSM Parameters     │  SSM Params   │
│                    └─────────────────────┴───────────────┘
│                                   │
├─ Compute Platform (Phase 6E) ─────┤
│  ECS Cluster → Task Definitions    │
│  IAM Roles → CloudWatch Logs      │
│                                   │
├─ Load Balancer (Phase 6F) ────────┤
│  ALB → Target Groups → Listeners  │
│                                   │
└─ Applications (Phase 6G) ─────────┘
   FastAPI Service → Celery Workers
   Bootstrap Endpoint → ECR Images
```

### Service Integration
- **FastAPI Application**: Connects to RDS, Redis, S3, SQS
- **Celery Workers**: Process background tasks from SQS
- **Load Balancer**: Routes traffic to FastAPI containers
- **Bootstrap Endpoint**: Creates initial admin API keys

### Deployment Scripts Available
- **`./scripts/deploy-infrastructure.sh`**: Complete infrastructure deployment (Phases 6A-6G)
  - Handles VPC, Storage, Database, Compute, Load Balancer, and Application deployment
  - Includes rollback functionality with `./scripts/deploy-infrastructure.sh rollback`
  - Performs health checks and outputs deployment summary
- **`./scripts/rebuild-images.sh`**: Build and push Docker images to ECR with correct architecture
  - Builds Docker images with `--platform linux/amd64` for ECS Fargate compatibility
  - Pushes to ECR and triggers ECS service redeployment
  - Essential for fixing architecture issues on Apple Silicon (ARM64) machines

---

## 📖 Resource Discovery Commands

Use these commands to find current resource IDs and states in your deployment:

### Terraform Outputs
```bash
# Navigate to Terraform directory
cd infrastructure/terraform/environments/dev

# Get all outputs
terraform output

# Get specific resource IDs
terraform output vpc_id
terraform output subnet_ids
terraform output rds_endpoint
terraform output redis_endpoint
terraform output s3_bucket_name
terraform output alb_dns_name
terraform output ecs_cluster_name
```

### AWS CLI Resource Discovery
```bash
# VPC and Networking
aws ec2 describe-vpcs --filters "Name=tag:Name,Values=youtube-downloader-dev-*"
aws ec2 describe-subnets --filters "Name=tag:Name,Values=youtube-downloader-dev-*"
aws ec2 describe-security-groups --filters "Name=tag:Name,Values=youtube-downloader-dev-*"

# Database and Cache
aws rds describe-db-instances --query 'DBInstances[?contains(DBInstanceIdentifier, `youtube-downloader-dev-postgres`)]'
aws elasticache describe-cache-clusters --query 'CacheClusters[?contains(CacheClusterId, `youtube-downloader-dev-redis`)]'

# ECS Resources
aws ecs list-clusters --query "clusterArns[?contains(@, 'youtube-downloader-dev')]"
aws ecs list-services --cluster <CLUSTER-NAME>

# Load Balancer
aws elbv2 describe-load-balancers --names youtube-do-dev-alb-*
aws elbv2 describe-target-groups --names youtube--dev-app-tg-*

# S3 and Storage
aws s3 ls | grep youtube-downloader-dev
```

### SSM Parameters
```bash
# Get all deployment parameters
aws ssm get-parameters-by-path --path "/youtube-downloader/dev" --recursive

# Specific connection strings
aws ssm get-parameter --name "/youtube-downloader/dev/database/host"
aws ssm get-parameter --name "/youtube-downloader/dev/redis/host"
aws ssm get-parameter --name "/youtube-downloader/dev/storage/s3_bucket_name"
```

---

## 💰 Cost Analysis by Category

### Monthly Cost Breakdown (Development Environment)

| Category | Service | Configuration | Monthly Cost | Notes |
|----------|---------|---------------|-------------|--------|
| **Networking** | VPC, Subnets, IGW, Security Groups | Standard configuration | $0.00 | Free tier eligible |
| **Storage** | S3 Standard | ~10GB expected usage | $0.25-0.50 | Based on usage patterns |
| **Database** | RDS PostgreSQL | db.t3.micro, 20GB, single-AZ | ~$12.00 | Cost optimized for dev |
| **Cache** | ElastiCache Redis | cache.t3.micro, single-node | ~$11.00 | Minimal caching needs |
| **Queues** | SQS + CloudWatch | Standard queues, basic alarms | ~$0.70 | Low volume expected |
| **Compute** | ECS Fargate | 2 services, 256 CPU, 512MB each | ~$15.00 | 24/7 operation |
| **Load Balancer** | Application Load Balancer | Standard ALB + capacity units | ~$21.00 | Internet-facing |

**Total Estimated Cost**: $59.95-60.20/month

### Cost Optimization Notes
- **Development Focus**: Single-AZ deployments reduce costs
- **Minimal Resources**: t3.micro instances for non-production workloads
- **Free Tier Usage**: VPC, basic monitoring, and data transfer included
- **Auto-scaling**: ECS can scale down to 0 for cost savings during idle periods

### Production Cost Considerations
For production deployment, expect ~2-3x cost increase due to:
- Multi-AZ database deployment (+$12-15/month)
- Larger instance sizes (+$20-30/month)
- SSL certificates and domain management (+$1/month)
- Enhanced monitoring and alerting (+$5-10/month)
- **Estimated Production Cost**: ~$140-180/month

---

## 🔧 Deployment Commands

### Initial Deployment

#### Automated Full Deployment (Recommended)
```bash
# Deploy complete infrastructure (Phases 6A-6G) automatically
./scripts/deploy-infrastructure.sh

# Alternative commands:
./scripts/deploy-infrastructure.sh plan     # Plan only (no changes)
./scripts/deploy-infrastructure.sh init     # Initialize Terraform only
./scripts/deploy-infrastructure.sh rollback # Destroy all resources
```

#### Manual Step-by-Step Deployment
```bash
# 1. Clone repository and navigate to Terraform
cd infrastructure/terraform/environments/dev

# 2. Initialize Terraform
terraform init

# 3. Plan deployment
terraform plan

# 4. Deploy infrastructure
terraform apply

# 5. Build and deploy applications
./scripts/rebuild-images.sh

# 6. Verify deployment (manual checks)
terraform output
aws ecs describe-services --cluster <CLUSTER-NAME> --services <APP-SERVICE>
curl http://<ALB-ENDPOINT>/health
```

### Resource Management
```bash
# Check infrastructure status
terraform show

# Update specific resources
terraform apply -target=module.database
terraform apply -target=module.compute

# View resource dependencies
terraform graph | dot -Tpng > infrastructure.png
```

### Application Updates
```bash
# Update application containers
./scripts/rebuild-images.sh

# Force ECS service redeployment
aws ecs update-service --cluster <CLUSTER-NAME> --service <SERVICE-NAME> --force-new-deployment

# Check deployment status
aws ecs describe-services --cluster <CLUSTER-NAME> --services <SERVICE-NAME>
```

---

## 🚨 Troubleshooting Guide

### Common Deployment Issues

#### Infrastructure Issues
**Problem**: Terraform deployment fails with resource conflicts
```bash
# Solution: Check existing resources
terraform state list
terraform import <resource_type>.<resource_name> <resource_id>
```

**Problem**: ECS tasks failing to start
```bash
# Check task definitions and logs
aws ecs describe-tasks --cluster <CLUSTER-NAME> --tasks <TASK-ARN>
aws logs get-log-events --log-group-name /ecs/youtube-downloader-dev-app
```

#### Application Issues
**Problem**: Health checks failing
```bash
# Check ALB target health
aws elbv2 describe-target-health --target-group-arn <TARGET-GROUP-ARN>

# Test health endpoint directly
curl http://<ALB-DNS-NAME>/health
```

**Problem**: Database connection issues
```bash
# Verify RDS endpoint and security groups
aws rds describe-db-instances --db-instance-identifier <DB-ID>
aws ec2 describe-security-groups --group-ids <SECURITY-GROUP-ID>
```

### Bootstrap Endpoint Issues
**Problem**: Cannot create initial admin API key
```bash
# Check bootstrap status
curl http://<ALB-DNS-NAME>/api/v1/bootstrap/status

# Verify environment variables
aws ecs describe-task-definition --task-definition <TASK-DEF-NAME>
```

---

## 🎯 Next Steps and Future Enhancements

### Current Phase 6G Status

#### ✅ What's Working
- **Infrastructure**: All AWS resources deployed and healthy
- **Services**: FastAPI and Celery containers running in ECS
- **Load Balancer**: ALB routing traffic with health checks passing
- **Bootstrap Endpoint**: Initial API key creation working (`/api/v1/bootstrap/admin-key`)
- **Basic API**: Health endpoint responding (`/health`)
- **Database**: PostgreSQL RDS connected with async driver
- **Authentication**: API key authentication system functional

#### 🚧 What Still Needs Testing
- **Video Download**: End-to-end YouTube video downloading not tested
- **File Storage**: S3 upload/download functionality not verified  
- **Background Tasks**: Celery job processing not tested with real tasks
- **WebSocket**: Real-time progress updates not tested
- **File Serving**: Video/subtitle file delivery not tested
- **Transcription**: YouTube subtitle extraction not verified

#### 🎯 Next Testing Steps
1. Test video info extraction: `GET /api/v1/info?url=<youtube-url>`
2. Test download job creation: `POST /api/v1/download`
3. Test job status tracking: `GET /api/v1/status/{job_id}`
4. Test WebSocket progress: `WS /ws/progress/{job_id}`
5. Verify file storage and serving functionality

### Phase 6H: Extended Production Features (Optional)

> **Reference**: See [AWS-INFRASTRUCTURE.md](AWS-INFRASTRUCTURE.md) "Option 3: Production Ready" for detailed production architecture planning.

#### 1. SSL Certificate and HTTPS
- Request ACM certificate for custom domain
- Configure HTTPS listener on ALB
- Set up domain with Route 53

#### 2. Enhanced Monitoring
- CloudWatch dashboards for key metrics
- SNS topics for alerting
- Application performance monitoring

#### 3. Security Hardening
- WAF integration with ALB
- VPC endpoints for AWS services
- Enhanced audit logging

#### 4. Performance Optimization
- Auto-scaling configuration (see [AWS-INFRASTRUCTURE.md](AWS-INFRASTRUCTURE.md) scaling policies)
- CloudFront CDN for static assets
- Database read replicas

### Estimated Timeline
- **SSL Setup**: 1-2 hours
- **Enhanced Monitoring**: 2-4 hours  
- **Security Hardening**: 4-6 hours
- **Performance Optimization**: 6-8 hours

---

## 📝 Deployment Log Template

Use this template to track your actual deployment:

### Current Deployment Information
```yaml
Deployment Date: [YYYY-MM-DD]
Environment: [dev/staging/prod]
Terraform Version: [version]
AWS Region: [us-east-1]
Deployed By: [name/team]

Resource IDs:
  VPC: [vpc-xxxxxxxxxx]
  Subnets: 
    - [subnet-xxxxxxxxxx]
    - [subnet-xxxxxxxxxx] 
  RDS Endpoint: [endpoint.region.rds.amazonaws.com]
  Redis Endpoint: [endpoint.cache.amazonaws.com]
  S3 Bucket: [bucket-name]
  ALB DNS: [alb-dns-name.region.elb.amazonaws.com]
  ECS Cluster: [cluster-name]

Application Status:
  FastAPI Service: [RUNNING/STOPPED]
  Celery Worker: [RUNNING/STOPPED]
  Bootstrap Endpoint: [ENABLED/DISABLED]
  Health Checks: [PASSING/FAILING]

Notes:
[Add any deployment-specific notes, issues encountered, or customizations made]
```

---

## 🔄 Rollback Procedures

### Emergency Rollback
```bash
# 1. Rollback application to previous images
aws ecs update-service --cluster <CLUSTER-NAME> --service <APP-SERVICE> --task-definition <PREVIOUS-TASK-DEF>

# 2. Rollback infrastructure (if needed)
cd infrastructure/terraform/environments/dev
terraform apply -target=module.<MODULE-NAME> -var="<PREVIOUS-CONFIG>"

# 3. Verify rollback success
terraform output  # Should show minimal or no resources
aws ecs list-clusters --query "clusterArns[?contains(@, 'youtube-downloader-dev')]"
```

### Complete Environment Teardown
```bash
# WARNING: This will destroy ALL resources
cd infrastructure/terraform/environments/dev
terraform destroy -auto-approve

# Clean up any remaining resources
aws s3 rm s3://<BUCKET-NAME> --recursive
aws s3api delete-bucket --bucket <BUCKET-NAME>
```

---

## 📚 Additional Resources

### Project Documentation
- **[AWS-INFRASTRUCTURE.md](AWS-INFRASTRUCTURE.md)**: Architecture planning, service configurations, scaling strategies, and cost analysis
- **[API.md](API.md)**: Complete API documentation, authentication guide, and endpoint examples
- **[../CLAUDE.md](../CLAUDE.md)**: Development commands, architecture overview, and local testing procedures

### AWS Documentation Links
- [Terraform AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [ECS Fargate Documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [Application Load Balancer Guide](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/)
- [RDS PostgreSQL Documentation](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)

### Support Commands
```bash
# Get AWS support case status
aws support describe-cases --language en

# Create support case (if needed)
aws support create-case --subject "ECS Deployment Issue" --service-code "amazon-elastic-container-service"
```

---

*Last Updated: [Auto-generated timestamp would go here]*  
*Document Version: 2.0 - Refactored for maintainability*