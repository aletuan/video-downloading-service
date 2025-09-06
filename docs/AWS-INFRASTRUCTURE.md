# AWS Infrastructure Planning

> Comprehensive guide for AWS deployment options, service configurations, and scaling strategies for the YouTube Video Download Service.

> **Related Documentation**: See [SUB-TASKS.md](SUB-TASKS.md) for current deployment status, operational procedures, and step-by-step deployment guide.

## Architecture Options Comparison

### Option 1: Ultra-Minimal Development (~$17-18/month)

**Target**: Initial development and testing with absolute minimal cost

```text
┌─────────────────────────────────────────┐
│              ECS Fargate                │
│  ┌─────────────────────────────────────┐│
│  │  FastAPI + Celery + PostgreSQL     ││
│  │  (Single Container)                 ││
│  │  0.5 vCPU, 1GB RAM                 ││
│  └─────────────────────────────────────┘│
└─────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────┐
│                S3 Bucket                │
│          (Video Storage)                │
└─────────────────────────────────────────┘
```

**Services:**

- **ECS Fargate**: Single all-in-one container
- **S3**: Basic video storage
- **VPC**: Public subnet only

****Monthly Cost: ~$17-18****

- ECS Fargate: ~$15/month
- S3 Storage (20GB): ~$1/month  
- VPC Basic: ~$1-2/month

### Option 2: Optimal Development (~$59-60/month) **CURRENTLY DEPLOYED**

**Target**: Proper development environment with managed services

```text
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   ECS Fargate   │    │   ECS Fargate   │    │                 │
│  ┌───────────┐  │    │  ┌───────────┐  │    │  RDS PostgreSQL │
│  │ FastAPI   │  │    │  │ Celery    │  │    │   db.t3.micro   │
│  │ 0.25 vCPU │  │    │  │ Worker    │  │    │   Single AZ     │
│  │ 0.5GB RAM │  │    │  │ 0.25 vCPU │  │    │                 │
│  └───────────┘  │    │  └───────────┘  │    └─────────────────┘
└─────────────────┘    └─────────────────┘
│                      │
▼                      ▼
┌──────────────────────────────────────────┐
│         ElastiCache Redis                │
│         cache.t3.micro                   │
└──────────────────────────────────────────┘
│
▼
┌──────────────────────────────────────────┐
│              S3 Bucket                   │
│          (Video Storage)                 │
└──────────────────────────────────────────┘
```

**Services:**

- **ECS Fargate**: Separate FastAPI and Celery containers
- **RDS PostgreSQL**: Managed database service
- **ElastiCache Redis**: Managed cache service
- **S3**: Video file storage
- **VPC**: Public subnets (no NAT Gateway)

**Monthly Cost: ~$59-60** (Currently Deployed Configuration)

- ECS Fargate (2 tasks): ~$15/month
- RDS PostgreSQL: ~$12/month
- ElastiCache Redis: ~$11/month
- Application Load Balancer: ~$21/month
- SQS + CloudWatch: ~$0.70/month
- S3 Storage (10GB): ~$0.25-0.50/month

### Option 3: Production Ready (~$355-705/month)

**Target**: Scalable production environment with high availability

```text
                    ┌─────────────────┐
                    │ Application     │
                    │ Load Balancer   │
                    └─────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ ECS Fargate     │ │ ECS Fargate     │ │ ECS Fargate     │
│ FastAPI         │ │ FastAPI         │ │ Celery Workers  │
│ Auto-scaling    │ │ Auto-scaling    │ │ Auto-scaling    │
│ 0.5-2 vCPU      │ │ 0.5-2 vCPU      │ │ 1-4 vCPU        │
└─────────────────┘ └─────────────────┘ └─────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ RDS PostgreSQL  │ │ElastiCache Redis│ │   S3 + CDN      │
│ Multi-AZ        │ │ Cluster Mode    │ │ CloudFront      │
│ db.t3.medium+   │ │ cache.t3.small+ │ │ Global Delivery │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

**Services:**

- **ECS Fargate**: Auto-scaling with ALB
- **RDS PostgreSQL**: Multi-AZ with read replicas
- **ElastiCache Redis**: Cluster mode enabled
- **S3 + CloudFront**: Global CDN
- **VPC**: Private subnets with NAT Gateway
- **ALB**: Application Load Balancer

## Service-by-Service Analysis

### ECS Fargate (Container Platform)

#### Purpose

- **Container Orchestration**: Serverless container platform
- **Auto-Scaling**: Scale based on CPU, memory, or custom metrics
- **No Server Management**: AWS manages underlying infrastructure
- **Pay-per-Use**: Only pay for running containers

#### Configuration Options

| Configuration | vCPU | Memory | Use Case | Monthly Cost* |
|---------------|------|--------|----------|---------------|
| **Micro** | 0.25 | 0.5GB | Dev/Testing | ~$7 |
| **Small** | 0.5 | 1GB | Light Production | ~$14 |
| **Medium** | 1.0 | 2GB | Standard Production | ~$29 |
| **Large** | 2.0 | 4GB | High Load | ~$58 |
| **XLarge** | 4.0 | 8GB | Heavy Processing | ~$116 |

*Based on 24/7 operation

#### Task Definitions

**FastAPI Application:**

```yaml
Family: youtube-downloader-api
CPU: 256 (0.25 vCPU) → 2048 (2 vCPU)
Memory: 512MB → 4GB
Port: 8000
Health Check: /health endpoint
Environment: Production settings
```

**Celery Worker:**

```yaml
Family: youtube-downloader-worker  
CPU: 256 (0.25 vCPU) → 4096 (4 vCPU)
Memory: 512MB → 8GB
Scaling: Queue-length based
Environment: Worker-specific settings
```

#### Auto-Scaling Policies

**Development:**

- Min: 1, Max: 2, Desired: 1
- Scale up: CPU > 70% for 5 minutes
- Scale down: CPU < 30% for 10 minutes

**Production:**

- Min: 2, Max: 10, Desired: 3
- Scale up: CPU > 60% or Queue > 10 jobs
- Scale down: CPU < 30% and Queue < 2 jobs

### RDS PostgreSQL (Database)

#### Purpose

- **Managed Database**: Automated backups, patching, monitoring
- **High Availability**: Multi-AZ deployment for failover
- **Performance**: Read replicas for scaling
- **Security**: Encryption at rest and in transit

#### Instance Types & Costs

| Instance Type | vCPU | Memory | Storage | Single AZ | Multi-AZ |
|---------------|------|--------|---------|-----------|----------|
| **db.t3.micro** | 2 | 1GB | 20GB | ~$12/month | ~$24/month |
| **db.t3.small** | 2 | 2GB | 100GB | ~$25/month | ~$50/month |
| **db.t3.medium** | 2 | 4GB | 100GB | ~$50/month | ~$100/month |
| **db.t3.large** | 2 | 8GB | 100GB | ~$100/month | ~$200/month |
| **db.r5.xlarge** | 4 | 32GB | 100GB | ~$300/month | ~$600/month |

#### Configuration Recommendations

**Development:**

- Instance: db.t3.micro
- Storage: 20GB General Purpose SSD
- Backup: 7-day retention
- Single AZ deployment

**Production:**

- Instance: db.t3.small+ (based on load)
- Storage: 100GB+ General Purpose SSD
- Backup: 30-day retention
- Multi-AZ deployment
- Read replicas for scaling

#### Connection Pooling

- Use PgBouncer or application-level pooling
- Recommended: 100-200 connections for db.t3.small
- Monitor: DatabaseConnections CloudWatch metric

### ElastiCache Redis (Cache Layer)

#### Purpose

- **Session Storage**: API key cache, user sessions
- **Job Queue**: Celery broker and result backend  
- **Application Cache**: Frequently accessed data
- **Rate Limiting**: Request throttling storage

#### Node Types & Costs

| Node Type | vCPU | Memory | Network | Monthly Cost |
|-----------|------|--------|---------|--------------|
| **cache.t3.micro** | 2 | 0.5GB | Low | ~$11/month |
| **cache.t3.small** | 2 | 1.37GB | Low-Med | ~$24/month |
| **cache.t3.medium** | 2 | 3.22GB | Med | ~$48/month |
| **cache.r5.large** | 2 | 13.07GB | High | ~$150/month |
| **cache.r5.xlarge** | 4 | 26.32GB | High | ~$300/month |

#### Configuration Options

**Development:**

- Node: cache.t3.micro
- Deployment: Single node
- Backup: Disabled
- Cluster Mode: Disabled

**Production:**

- Node: cache.t3.small+
- Deployment: Multi-AZ with failover
- Backup: Daily snapshots
- Cluster Mode: Enabled for scaling

### S3 + CloudFront (Storage & CDN)

#### S3 Storage Purpose

- **Video Files**: Downloaded MP4/WebM files
- **Transcripts**: SRT, VTT, TXT files
- **Static Assets**: Thumbnails, metadata
- **Backups**: Database and application backups

#### Storage Classes & Costs

| Storage Class | Use Case | Cost per GB/month |
|---------------|----------|-------------------|
| **Standard** | Frequently accessed videos | $0.023 |
| **Infrequent Access** | Older videos | $0.0125 |
| **Glacier** | Archive/compliance | $0.004 |
| **Deep Archive** | Long-term backup | $0.00099 |

#### CloudFront CDN

**Development**: Skip CDN (direct S3 access)

- Cost: $0
- Latency: Higher for global users
- Bandwidth: Direct S3 transfer costs

**Production**: Global CDN

- Cost: $0.085-0.25 per GB transferred
- Latency: Global edge locations
- Bandwidth: Reduced origin requests

### Networking (VPC, ALB, NAT Gateway)

#### VPC Configuration

**Development:**

```text
- Public Subnets: 2 AZs
- Private Subnets: None
- NAT Gateway: None (cost saving)
- Internet Gateway: Yes
- Cost: ~$2/month
```

**Production:**

```text
- Public Subnets: 2 AZs (ALB)
- Private Subnets: 2 AZs (ECS, RDS)
- NAT Gateway: 2 (Multi-AZ)
- Internet Gateway: Yes  
- Cost: ~$110/month
```

#### Application Load Balancer (ALB)

**Development**: Skip ALB

- Access: Direct ECS service endpoints
- Cost: $0
- Features: No SSL termination, path-based routing

**Production**: ALB Required

- Cost: ~$18/month base + $0.008/LCU-hour
- Features: SSL termination, health checks, auto-scaling integration
- Security: WAF integration, DDoS protection

## Scaling Decision Matrix

### When to Upgrade Each Service

#### ECS Fargate Scaling Triggers

| Metric | Dev → Production | Scale Up Within Prod |
|--------|------------------|----------------------|
| **CPU Usage** | >80% sustained | >70% for 5min |
| **Memory Usage** | >85% sustained | >80% for 5min |
| **Queue Length** | >20 jobs | >10 jobs |
| **Response Time** | >2 seconds | >1 second |

#### Database Scaling Triggers

| Metric | Upgrade Instance | Add Read Replica |
|--------|------------------|------------------|
| **CPU Usage** | >70% sustained | >60% on reads |
| **Connections** | >80% of max | >50 concurrent read queries |
| **Storage** | >80% used | N/A |
| **IOPS** | Consistent throttling | High read IOPS |

#### Cache Scaling Triggers

| Metric | Upgrade Node | Enable Cluster |
|--------|--------------|----------------|
| **Memory Usage** | >80% used | >70% on single node |
| **Evictions** | >100/hour | Consistent evictions |
| **CPU Usage** | >70% sustained | >50% with high ops |

### Cost Break-Even Analysis

#### Traffic-Based Scaling

```text
Light Usage (0-1000 downloads/day):
- Ultra-Minimal: $17/month
- Optimal Dev: $40/month  
- Break-even: When development features needed

Medium Usage (1000-10000 downloads/day):
- Optimal Dev: $40/month
- Production: $200/month
- Break-even: When reliability/performance critical

Heavy Usage (10000+ downloads/day):
- Production: $200-400/month
- Enterprise: $500+/month  
- Break-even: When advanced features needed
```

## Terraform Module Structure

### Recommended Organization

```text
infrastructure/
├── terraform/
│   ├── environments/
│   │   ├── dev/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── terraform.tfvars
│   │   └── prod/
│   │       ├── main.tf
│   │       ├── variables.tf
│   │       └── terraform.tfvars
│   ├── modules/
│   │   ├── networking/
│   │   │   ├── vpc.tf
│   │   │   ├── subnets.tf
│   │   │   └── security-groups.tf
│   │   ├── database/
│   │   │   ├── rds.tf
│   │   │   └── elasticache.tf
│   │   ├── compute/
│   │   │   ├── ecs.tf
│   │   │   ├── task-definitions.tf
│   │   │   └── auto-scaling.tf
│   │   └── storage/
│   │       ├── s3.tf
│   │       └── cloudfront.tf
│   └── shared/
│       ├── backend.tf
│       └── providers.tf
```

### Environment Configuration Strategy

#### Development Variables

```hcl
# dev/terraform.tfvars
environment = "dev"
ecs_cpu = 256
ecs_memory = 512
rds_instance_class = "db.t3.micro"
redis_node_type = "cache.t3.micro"
enable_multi_az = false
enable_cloudfront = false
```

#### Production Variables  

```hcl
# prod/terraform.tfvars
environment = "prod"
ecs_cpu = 1024
ecs_memory = 2048
rds_instance_class = "db.t3.medium"
redis_node_type = "cache.t3.small"
enable_multi_az = true
enable_cloudfront = true
```

### Shared Module Parameters

```hcl
variable "environment" {
  description = "Environment name (dev/staging/prod)"
  type        = string
}

variable "instance_sizes" {
  description = "Instance sizing based on environment"
  type = object({
    ecs_cpu           = number
    ecs_memory        = number
    rds_instance_class = string
    redis_node_type   = string
  })
}

variable "feature_flags" {
  description = "Environment-specific feature toggles"
  type = object({
    enable_multi_az      = bool
    enable_cloudfront    = bool
    enable_nat_gateway   = bool
    enable_load_balancer = bool
  })
}
```

## Implementation Recommendations

### Phase 1: Start with Optimal Development

1. **Low Risk**: Manageable complexity and cost
2. **Learning**: Experience with core AWS services
3. **Scalable**: Clear path to production
4. **Cost Effective**: ~$40/month provides real managed services

### Phase 2: Add Production Features Gradually

1. **Multi-AZ**: Add database redundancy
2. **Load Balancer**: Add ALB for traffic distribution
3. **Auto-scaling**: Implement dynamic scaling
4. **CDN**: Add CloudFront for global delivery

### Phase 3: Advanced Production Features

1. **Monitoring**: CloudWatch dashboards and alarms
2. **Security**: WAF, VPC Flow Logs, GuardDuty
3. **Performance**: Read replicas, ElastiCache clustering
4. **Compliance**: Backup automation, encryption

## Current Implementation Status

**Completed (Phase 6G)**: The "Optimal Development" configuration has been successfully deployed to AWS:

- All infrastructure components operational
- FastAPI and Celery services running on ECS Fargate
- Bootstrap endpoint implemented for production API key management
- Load balancer health checks passing

**Next Steps**: See [SUB-TASKS.md](SUB-TASKS.md) for:

- Current deployment status details
- End-to-end testing procedures
- Production upgrade path (Phase 6H)
- Operational troubleshooting guides

## Related Documentation

- **[SUB-TASKS.md](SUB-TASKS.md)**: Current deployment status, operational procedures, and testing guide
- **[API.md](API.md)**: API endpoint documentation and authentication setup
- **[../scripts/deploy-infrastructure.sh](../scripts/deploy-infrastructure.sh)**: Automated deployment script
- **[../scripts/rebuild-images.sh](../scripts/rebuild-images.sh)**: Docker image build and deployment script

This infrastructure plan provided the foundation for the current AWS deployment, achieving a balance between cost-effectiveness (~$60/month) and production-ready features.
