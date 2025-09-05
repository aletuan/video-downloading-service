# Deployment Guide

## AWS Deployment

The service is designed for AWS deployment with:
- **ECS/Fargate** for container orchestration
- **RDS PostgreSQL** for database
- **ElastiCache Redis** for caching
- **S3** for video storage
- **CloudFront** for content delivery

## Environment Detection

The service automatically detects its environment:
- **Local Development**: Uses local filesystem storage
- **AWS Cloud**: Uses S3 with CloudFront integration

## Configuration for Production

### Environment Variables

Set these environment variables for AWS deployment:

```env
# Environment Detection
ENVIRONMENT=aws
DEBUG=false

# Database
DATABASE_URL=postgresql+asyncpg://username:password@rds-endpoint:5432/dbname

# Redis Cache
REDIS_URL=redis://elasticache-endpoint:6379/0

# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_REGION=us-east-1

# S3 Storage
S3_BUCKET_NAME=your-video-storage-bucket
S3_CLOUDFRONT_DOMAIN=your-distribution.cloudfront.net

# Application Settings
DOWNLOAD_BASE_PATH=/tmp/downloads
```

### AWS Services Setup

#### 1. RDS PostgreSQL
- Create an RDS PostgreSQL instance
- Configure security groups for application access
- Set up connection pooling if needed
- Enable automated backups

#### 2. ElastiCache Redis
- Create Redis cluster
- Configure security groups
- Enable encryption in transit and at rest
- Set appropriate memory limits

#### 3. S3 Bucket
- Create S3 bucket for video storage
- Configure bucket policies and CORS
- Enable versioning if required
- Set up lifecycle policies for cost optimization

#### 4. CloudFront Distribution
- Create CloudFront distribution pointing to S3 bucket
- Configure caching behaviors
- Set up custom domain if needed
- Enable compression

#### 5. ECS/Fargate
- Create ECS cluster
- Define task definitions for app and worker
- Configure service scaling policies
- Set up load balancer
- Configure health checks

## Monitoring & Health Checks

The service includes comprehensive health monitoring:

- **Basic Health**: `GET /health` - Simple status check
- **Detailed Health**: `GET /health/detailed` - Full system validation including:
  - Database connectivity and version
  - Storage handler read/write validation (Local/S3)
  - System environment detection

```bash
# Test health endpoints
curl http://localhost:8000/health
curl http://localhost:8000/health/detailed | jq .

# Test Celery worker
docker compose exec celery-worker celery -A app.tasks.download_tasks inspect ping
```

## Security Considerations

### API Keys in Production
- Generate strong admin API keys
- Use different keys for different applications/users
- Implement key rotation policies
- Monitor API key usage

### Network Security
- Use VPC with private subnets
- Configure security groups with minimal required access
- Enable AWS WAF for web application firewall
- Use TLS/SSL for all connections

### Data Protection
- Enable encryption at rest for RDS and S3
- Use IAM roles instead of access keys where possible
- Configure backup and disaster recovery
- Implement audit logging

## Scaling Considerations

### Horizontal Scaling
- Configure auto-scaling for ECS services
- Use Application Load Balancer for distribution
- Scale Celery workers based on queue length
- Monitor and scale Redis if needed

### Performance Optimization
- Use CloudFront CDN for video delivery
- Implement connection pooling for database
- Configure appropriate cache TTLs
- Monitor and optimize S3 storage classes

## Maintenance

### Database Migrations
```bash
# Run migrations in production
alembic upgrade head
```

### Monitoring
- Set up CloudWatch alarms for key metrics
- Monitor application logs
- Track API response times and error rates
- Monitor storage usage and costs

### Backup Strategy
- Automated RDS backups
- S3 versioning for critical data
- Regular testing of restore procedures
- Document recovery procedures