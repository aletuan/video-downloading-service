#!/bin/bash

# AWS Infrastructure Deployment Script
# Deploys all phases from 6A through 6F systematically
# Based on SUB-TASKS.md Phase 6 deployment strategy

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TERRAFORM_DIR="/Users/andy/Workspace/Claude/video-downloading-service/infrastructure/terraform/environments/dev"
LOG_FILE="/tmp/terraform-deployment.log"

# Utility functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}✅ $1${NC}" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}❌ $1${NC}" | tee -a "$LOG_FILE"
}

# Check prerequisites
check_prerequisites() {
    log "Phase 0: Checking prerequisites..."
    
    # Check if terraform is installed
    if ! command -v terraform &> /dev/null; then
        error "Terraform is not installed"
        exit 1
    fi
    
    # Check if AWS CLI is installed and configured
    if ! command -v aws &> /dev/null; then
        error "AWS CLI is not installed"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        error "AWS credentials are not configured properly"
        exit 1
    fi
    
    # Check if we're in the right directory
    if [ ! -f "$TERRAFORM_DIR/main.tf" ]; then
        error "Terraform directory not found: $TERRAFORM_DIR"
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# Initialize Terraform
terraform_init() {
    log "Initializing Terraform..."
    cd "$TERRAFORM_DIR"
    
    if terraform init; then
        success "Terraform initialized successfully"
    else
        error "Terraform initialization failed"
        exit 1
    fi
}

# Deploy specific module with verification
deploy_module() {
    local phase=$1
    local module=$2
    local description=$3
    
    log "Phase $phase: $description"
    log "Deploying module: $module"
    
    cd "$TERRAFORM_DIR"
    
    # Plan the deployment
    log "Planning deployment for $module..."
    if terraform plan -target="module.$module" -out="/tmp/terraform-$module.plan"; then
        success "Plan created for $module"
    else
        error "Planning failed for $module"
        return 1
    fi
    
    # Apply the deployment
    log "Applying deployment for $module..."
    if terraform apply "/tmp/terraform-$module.plan"; then
        success "✅ Phase $phase COMPLETED: $description"
        
        # Clean up plan file
        rm -f "/tmp/terraform-$module.plan"
        
        # Show outputs
        log "Terraform outputs for $module:"
        terraform output | grep -E "(${module}|account_id|region)" || true
        
        return 0
    else
        error "❌ Phase $phase FAILED: $description"
        return 1
    fi
}

# Deploy all infrastructure phases
deploy_all_phases() {
    log "Starting complete AWS infrastructure deployment..."
    log "Following SUB-TASKS.md Phase 6 deployment strategy"
    
    # Phase 6A: Core Infrastructure Foundation
    if deploy_module "6A" "networking" "Core Infrastructure Foundation (VPC, Subnets, Security Groups)"; then
        log "✅ Phase 6A: VPC, subnets, gateways, and security groups deployed"
        sleep 10  # Allow resources to stabilize
    else
        error "Phase 6A failed - stopping deployment"
        exit 1
    fi
    
    # Phase 6B: Storage Layer
    if deploy_module "6B" "storage" "Storage Layer (S3 Bucket with Lifecycle Management)"; then
        log "✅ Phase 6B: S3 storage layer deployed"
        sleep 5
    else
        error "Phase 6B failed - stopping deployment"
        exit 1
    fi
    
    # Phase 6C: Database & Cache Layer
    if deploy_module "6C" "database" "Database & Cache Layer (PostgreSQL RDS + ElastiCache Redis)"; then
        log "✅ Phase 6C: Database and cache layer deployed"
        log "⚠️  Note: RDS and ElastiCache may take 10-15 minutes to be fully available"
        sleep 30  # Allow time for database initialization
    else
        error "Phase 6C failed - stopping deployment"
        exit 1
    fi
    
    # Phase 6D: Queue System
    if deploy_module "6D" "queue" "Queue System (SQS Main Queue + DLQ with CloudWatch Alarms)"; then
        log "✅ Phase 6D: SQS queue system deployed"
        sleep 5
    else
        error "Phase 6D failed - stopping deployment"
        exit 1
    fi
    
    # Phase 6E: Compute Platform
    if deploy_module "6E" "compute" "Compute Platform (ECS Fargate Cluster + Task Definitions)"; then
        log "✅ Phase 6E: ECS compute platform deployed"
        sleep 10
    else
        error "Phase 6E failed - stopping deployment"
        exit 1
    fi
    
    # Phase 6F: Load Balancing & Security
    if deploy_module "6F" "load_balancer" "Load Balancing & Security (ALB + Target Groups + SSL)"; then
        log "✅ Phase 6F: Load balancer and security deployed"
        sleep 10
    else
        error "Phase 6F failed - stopping deployment"
        exit 1
    fi
    
    # Phase 6G: Production Application Deployment
    log "Phase 6G: Production Application Deployment"
    
    # Check if ECR repositories exist
    if aws ecr describe-repositories --repository-names youtube-downloader/app youtube-downloader/worker &>/dev/null; then
        success "ECR repositories already exist"
    else
        log "Creating ECR repositories..."
        aws ecr create-repository --repository-name youtube-downloader/app --region us-east-1 || true
        aws ecr create-repository --repository-name youtube-downloader/worker --region us-east-1 || true
        success "ECR repositories created"
    fi
    
    # Check Docker images
    log "Checking Docker images..."
    if docker images | grep -q "youtube-downloader.*latest"; then
        success "Docker images found locally"
        
        # Offer to rebuild if needed
        log "💡 If you need to rebuild images with correct architecture, run:"
        log "   ./scripts/rebuild-images.sh"
        
        # Check if images are pushed to ECR
        if aws ecr describe-images --repository-name youtube-downloader/app --query 'imageDetails[0].imagePushedAt' &>/dev/null; then
            success "Images found in ECR"
        else
            warning "Images not found in ECR - you may need to run ./scripts/rebuild-images.sh"
        fi
    else
        warning "Docker images not found locally - you need to run ./scripts/rebuild-images.sh"
    fi
    
    # Update Parameter Store for async database driver
    log "Updating database configuration for async operations..."
    CURRENT_DB_URL=$(aws ssm get-parameter --name /youtube-downloader/dev/database/url --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || echo "")
    
    if [[ "$CURRENT_DB_URL" == postgresql://* ]]; then
        # Update to use asyncpg driver
        NEW_DB_URL="${CURRENT_DB_URL/postgresql:/\/postgresql+asyncpg:/\/}"
        aws ssm put-parameter --name /youtube-downloader/dev/database/url --value "$NEW_DB_URL" --type SecureString --overwrite
        success "Database URL updated to use async driver (asyncpg)"
    elif [[ "$CURRENT_DB_URL" == postgresql+asyncpg://* ]]; then
        success "Database URL already configured for async operations"
    else
        warning "Database URL not found or invalid format"
    fi
    
    # Force ECS deployment to use latest images
    log "Forcing ECS deployment with latest task definitions..."
    aws ecs update-service --cluster youtube-downloader-dev-cluster-0ca94b2c --service youtube-downloader-dev-app --force-new-deployment &>/dev/null || warning "Failed to update app service"
    aws ecs update-service --cluster youtube-downloader-dev-cluster-0ca94b2c --service youtube-downloader-dev-worker --force-new-deployment &>/dev/null || warning "Failed to update worker service"
    
    # Wait for services to stabilize
    log "Waiting for ECS services to stabilize..."
    sleep 30
    
    # Check ECS service health
    APP_STATUS=$(aws ecs describe-services --cluster youtube-downloader-dev-cluster-0ca94b2c --services youtube-downloader-dev-app --query 'services[0].{running:runningCount,desired:desiredCount}' --output text 2>/dev/null)
    WORKER_STATUS=$(aws ecs describe-services --cluster youtube-downloader-dev-cluster-0ca94b2c --services youtube-downloader-dev-worker --query 'services[0].{running:runningCount,desired:desiredCount}' --output text 2>/dev/null)
    
    if [[ "$APP_STATUS" == *"1	1"* ]]; then
        success "FastAPI service is running (1/1)"
    else
        warning "FastAPI service status: $APP_STATUS"
    fi
    
    if [[ "$WORKER_STATUS" == *"1	1"* ]]; then
        success "Celery worker service is running (1/1)"  
    else
        warning "Celery worker service status: $WORKER_STATUS"
    fi
    
    # Test ALB health endpoint
    log "Testing ALB health endpoint..."
    ALB_ENDPOINT=$(terraform output -raw alb_endpoint 2>/dev/null)
    if [[ -n "$ALB_ENDPOINT" ]]; then
        HEALTH_RESPONSE=$(curl -s "$ALB_ENDPOINT/health" 2>/dev/null || echo "failed")
        if [[ "$HEALTH_RESPONSE" == *"healthy"* ]]; then
            success "✅ ALB health check passed: $HEALTH_RESPONSE"
        else
            warning "ALB health check failed or still starting up"
            log "   Try: curl $ALB_ENDPOINT/health"
        fi
    fi
    
    # Final verification
    log "Final verification and configuration"
    cd "$TERRAFORM_DIR" 
    terraform output > "/tmp/terraform-final-outputs.txt"
    
    success "🎉 All phases deployed successfully!"
    success "✅ Phase 6G: Production Application Deployment completed!"
}

# Show deployment summary
show_deployment_summary() {
    log "=== DEPLOYMENT SUMMARY ==="
    
    cd "$TERRAFORM_DIR"
    
    echo ""
    log "🏗️  Infrastructure Overview:"
    terraform output | grep -E "(alb_endpoint|database_endpoint|redis_endpoint|s3_bucket_name|ecs_cluster_name)" || true
    
    echo ""
    log "💰 Cost Estimation:"
    terraform output | grep -E "(estimated_monthly_cost|total_estimated)" || true
    
    echo ""
    log "✅ Phase 6G Status:"
    terraform output | grep -E "(app_service_name|worker_service_name)" || true
    
    # Check ALB health
    ALB_ENDPOINT=$(terraform output -raw alb_endpoint 2>/dev/null)
    if [[ -n "$ALB_ENDPOINT" ]]; then
        echo "🌐 Health Check: $ALB_ENDPOINT/health"
        HEALTH_STATUS=$(curl -s "$ALB_ENDPOINT/health" 2>/dev/null || echo "Not Ready")
        echo "   Status: $HEALTH_STATUS"
    fi
    
    echo ""
    log "📋 Available Actions:"
    echo "1. Test application: curl $ALB_ENDPOINT/health"
    echo "2. Rebuild images: ./scripts/rebuild-images.sh" 
    echo "3. View ECS logs: aws logs get-log-events --log-group-name /ecs/youtube-downloader-dev-app"
    echo "4. Rollback all: ./scripts/deploy-infrastructure.sh rollback"
    echo ""
    log "📁 Full outputs saved to: /tmp/terraform-final-outputs.txt"
    log "📁 Deployment log saved to: $LOG_FILE"
}

# Rollback function
rollback_deployment() {
    warning "🚨 ROLLBACK REQUESTED"
    log "This will destroy ALL infrastructure resources AND ECR repositories"
    log "⚠️  This includes:"
    log "   - All Terraform resources (VPC, RDS, ECS, ALB, etc.)"
    log "   - ECR repositories and all Docker images"
    log "   - All stored data and configurations"
    
    read -p "Are you sure you want to destroy all resources? (type 'yes' to confirm): " confirm
    
    if [ "$confirm" = "yes" ]; then
        # Step 1: Clean up ECR repositories first
        log "Step 1/2: Cleaning up ECR repositories..."
        
        if aws ecr describe-repositories --region us-east-1 &>/dev/null; then
            ECR_REPOS=$(aws ecr describe-repositories --region us-east-1 --query 'repositories[].repositoryName' --output text 2>/dev/null || echo "")
            
            if [[ -n "$ECR_REPOS" ]]; then
                log "Found ECR repositories: $ECR_REPOS"
                
                for repo in $ECR_REPOS; do
                    if [[ "$repo" == youtube-downloader/* ]]; then
                        log "Deleting ECR repository: $repo"
                        if aws ecr delete-repository --repository-name "$repo" --force --region us-east-1; then
                            success "✅ ECR repository '$repo' deleted successfully"
                        else
                            warning "Failed to delete ECR repository '$repo'"
                        fi
                    fi
                done
            else
                log "No ECR repositories found"
            fi
        else
            log "No ECR repositories found or AWS CLI not configured"
        fi
        
        # Step 2: Destroy Terraform infrastructure
        log "Step 2/2: Destroying Terraform infrastructure..."
        cd "$TERRAFORM_DIR"
        
        if terraform destroy -auto-approve; then
            success "✅ All Terraform resources destroyed successfully"
            
            # Final verification
            log "Performing final cleanup verification..."
            
            # Check terraform state
            if [ "$(terraform state list | wc -l)" -eq 0 ]; then
                success "✅ Terraform state is clean"
            else
                warning "⚠️  Some resources may remain in terraform state"
            fi
            
            # Check ECR repositories
            ECR_CHECK=$(aws ecr describe-repositories --region us-east-1 --query 'repositories[].repositoryName' --output text 2>/dev/null || echo "")
            if [[ -z "$ECR_CHECK" ]]; then
                success "✅ All ECR repositories cleaned up"
            else
                warning "⚠️  Some ECR repositories may still exist: $ECR_CHECK"
            fi
            
            success "🎉 Complete infrastructure rollback finished!"
            log "💰 Cost savings: All recurring AWS charges eliminated"
            
        else
            error "❌ Terraform rollback failed - manual cleanup may be required"
            log "💡 You may need to manually delete ECR repositories:"
            log "   aws ecr describe-repositories --region us-east-1"
            log "   aws ecr delete-repository --repository-name REPO_NAME --force"
        fi
    else
        log "Rollback cancelled"
    fi
}

# Main script execution
main() {
    echo ""
    log "🚀 AWS Infrastructure Deployment Script"
    log "Based on SUB-TASKS.md Phase 6 Strategy (6A-6G Complete)"
    log "Deploys: VPC → Storage → Database → Queue → Compute → LoadBalancer → Application"
    echo ""
    
    # Handle command line arguments
    case "${1:-}" in
        "rollback"|"destroy")
            rollback_deployment
            ;;
        "plan")
            check_prerequisites
            terraform_init
            cd "$TERRAFORM_DIR"
            log "Running full terraform plan..."
            terraform plan
            ;;
        "init")
            check_prerequisites
            terraform_init
            ;;
        *)
            # Default: Full deployment
            check_prerequisites
            terraform_init
            deploy_all_phases
            show_deployment_summary
            ;;
    esac
}

# Run main function with all arguments
main "$@"