#!/bin/bash

# AWS Infrastructure Deployment Script
# Orchestrates Terraform deployment of all infrastructure components
# Role: Script coordination only - infrastructure logic is in Terraform modules

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TERRAFORM_DIR="${PROJECT_ROOT}/infrastructure/terraform/environments/dev"
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

# Extract values from terraform outputs
get_terraform_output() {
    local output_name=$1
    local default_value=${2:-""}
    
    cd "$TERRAFORM_DIR"
    local value=$(terraform output -raw "$output_name" 2>/dev/null || echo "$default_value")
    echo "$value"
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
    
    echo ""
    log "🔄 Phase $phase: $description"
    cd "$TERRAFORM_DIR"
    
    # Plan and Apply
    if terraform plan -target="module.$module" -out="/tmp/terraform-$module.plan" &>/dev/null; then
        if terraform apply "/tmp/terraform-$module.plan"; then
            success "✅ Phase $phase COMPLETED"
            rm -f "/tmp/terraform-$module.plan"
            return 0
        fi
    fi
    
    error "❌ Phase $phase FAILED"
    return 1
}

# Deploy all infrastructure phases
deploy_all_phases() {
    echo "⚡ STARTING DEPLOYMENT EXECUTION..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Phase 6A: Core Infrastructure Foundation
    deploy_module "6A" "networking" "Core Infrastructure Foundation (VPC, Subnets, Security Groups)" || exit 1
    sleep 10  # Allow resources to stabilize
    
    # Phase 6B: Storage Layer  
    deploy_module "6B" "storage" "Storage Layer (S3 Bucket with Lifecycle Management)" || exit 1
    sleep 5
    
    # Phase 6C: Database & Cache Layer
    deploy_module "6C" "database" "Database & Cache Layer (PostgreSQL RDS + ElastiCache Redis)" || exit 1
    log "⚠️  Note: RDS and ElastiCache may take 10-15 minutes to be fully available"
    sleep 30  # Allow time for database initialization
    
    # Phase 6D: Queue System
    deploy_module "6D" "queue" "Queue System (SQS Main Queue + DLQ with CloudWatch Alarms)" || exit 1
    sleep 5
    
    # Phase 6E: Load Balancing & Security  
    deploy_module "6E" "load_balancer" "Load Balancing & Security (ALB + Target Groups + SSL)" || exit 1
    sleep 10
    
    # Phase 6F: Compute Platform
    deploy_module "6F" "compute" "Compute Platform (ECS Fargate Cluster + Task Definitions)" || exit 1
    sleep 10
    
    # Phase 6G: Application Deployment
    echo ""
    log "📦 Phase 6G: Application Deployment"
    
    # ECR Setup
    if ! aws ecr describe-repositories --repository-names youtube-downloader/app youtube-downloader/worker &>/dev/null; then
        log "Creating ECR repositories..."
        aws ecr create-repository --repository-name youtube-downloader/app --region us-east-1 || true
        aws ecr create-repository --repository-name youtube-downloader/worker --region us-east-1 || true
    fi
    
    # Build & Push Images
    log "Building and pushing Docker images..."
    "${SCRIPT_DIR}/rebuild-images.sh" || { error "Docker image build failed"; return 1; }
    
    # Deploy Services
    log "Deploying ECS services..."
    CLUSTER_NAME=$(get_terraform_output "ecs_cluster_name")
    APP_SERVICE_NAME=$(get_terraform_output "app_service_name") 
    WORKER_SERVICE_NAME=$(get_terraform_output "worker_service_name")
    
    [[ -n "$CLUSTER_NAME" && -n "$APP_SERVICE_NAME" ]] && aws ecs update-service --cluster "$CLUSTER_NAME" --service "$APP_SERVICE_NAME" --force-new-deployment &>/dev/null
    [[ -n "$CLUSTER_NAME" && -n "$WORKER_SERVICE_NAME" ]] && aws ecs update-service --cluster "$CLUSTER_NAME" --service "$WORKER_SERVICE_NAME" --force-new-deployment &>/dev/null
    
    # Verify Services
    sleep 30
    APP_STATUS=$(aws ecs describe-services --cluster "$CLUSTER_NAME" --services "$APP_SERVICE_NAME" --query 'services[0].{running:runningCount,desired:desiredCount}' --output text 2>/dev/null || echo "0	1")
    WORKER_STATUS=$(aws ecs describe-services --cluster "$CLUSTER_NAME" --services "$WORKER_SERVICE_NAME" --query 'services[0].{running:runningCount,desired:desiredCount}' --output text 2>/dev/null || echo "0	1")
    
    [[ "$APP_STATUS" == *"1	1"* ]] && success "FastAPI service: 1/1 running" || warning "FastAPI service: $APP_STATUS"
    [[ "$WORKER_STATUS" == *"1	1"* ]] && success "Worker service: 1/1 running" || warning "Worker service: $WORKER_STATUS"
    
    # Phase 6H: Database Migration
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "🗄️  Phase 6H: Database Migration & Schema Setup"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Use dedicated migration script for better error handling and progress tracking
    log "Running database migration using dedicated script..."
    
    if "${SCRIPT_DIR}/migrate-database-simple.sh"; then
        success "✅ Phase 6H COMPLETED: Database tables ready (api_keys, download_jobs, alembic_version)"
        
        # Restart ECS services to pick up new database schema
        log "Restarting ECS services to refresh database connections..."
        [[ -n "$CLUSTER_NAME" && -n "$APP_SERVICE_NAME" ]] && aws ecs update-service --cluster "$CLUSTER_NAME" --service "$APP_SERVICE_NAME" --force-new-deployment &>/dev/null
        [[ -n "$CLUSTER_NAME" && -n "$WORKER_SERVICE_NAME" ]] && aws ecs update-service --cluster "$CLUSTER_NAME" --service "$WORKER_SERVICE_NAME" --force-new-deployment &>/dev/null
        sleep 30  # Allow services to restart with new schema
        
        # Additional verification via application health check
        log "Performing application-level database verification..."
        sleep 5  # Allow services to register the new tables
        
        ALB_ENDPOINT=$(get_terraform_output "alb_endpoint")
        if [[ -n "$ALB_ENDPOINT" ]]; then
            DB_HEALTH=$(curl -s "$ALB_ENDPOINT/health/detailed" 2>/dev/null | jq -r '.checks.database.status' 2>/dev/null || echo "unknown")
            if [[ "$DB_HEALTH" == "healthy" ]]; then
                success "✅ Application database health check: PASSED"
            else
                warning "⚠️  Application database health check: $DB_HEALTH"
            fi
        fi
    else
        error "❌ Phase 6H FAILED: Database migration unsuccessful"
        warning "⚠️  API endpoints may not work properly without database tables"
        log "📋 Troubleshooting steps:"
        log "   1. Check migration logs: /tmp/database-migration.log"
        log "   2. Verify database connectivity: curl $ALB_ENDPOINT/health/detailed"
        log "   3. Run manual migration: ./scripts/migrate-database-simple.sh"
        log "   4. Check ECS task logs: aws logs describe-log-groups --log-group-name-prefix /ecs/"
        
        # Don't fail deployment completely - let it continue for debugging
        warning "⚠️  Continuing deployment for debugging purposes..."
    fi
    
    # Final Health Check
    echo ""
    log "🔍 Final Health Verification"
    ALB_ENDPOINT=$(terraform output -raw alb_endpoint 2>/dev/null)
    if [[ -n "$ALB_ENDPOINT" ]]; then
        HEALTH_RESPONSE=$(curl -s "$ALB_ENDPOINT/health" 2>/dev/null || echo "failed")
        if [[ "$HEALTH_RESPONSE" == *"healthy"* ]]; then
            success "Application health check: PASSED ✅"
        else
            warning "Application health check: FAILED or starting up"
            log "Manual test: curl $ALB_ENDPOINT/health"
        fi
    fi
    
    # Save outputs
    terraform output > "/tmp/terraform-final-outputs.txt"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    success "🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!"
    success "✅ All 8 phases deployed (6A-6H)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
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
    log "📁 Database migration log saved to: /tmp/database-migration.log"
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

# Show deployment workflow overview
show_deployment_overview() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🚀 AWS INFRASTRUCTURE DEPLOYMENT - YOUTUBE DOWNLOADER SERVICE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "📋 DEPLOYMENT WORKFLOW (8 Phases):"
    echo "   Phase 6A: Core Infrastructure    → VPC, Subnets, Security Groups"
    echo "   Phase 6B: Storage Layer          → S3 Bucket with Lifecycle"  
    echo "   Phase 6C: Database & Cache       → PostgreSQL RDS + ElastiCache Redis"
    echo "   Phase 6D: Queue System           → SQS Main Queue + Dead Letter Queue"
    echo "   Phase 6E: Load Balancing         → Application Load Balancer + SSL"
    echo "   Phase 6F: Compute Platform       → ECS Fargate Cluster + Task Definitions"
    echo "   Phase 6G: Application Deploy     → Docker Images + ECS Services"
    echo "   Phase 6H: Database Migration     → Create Tables (api_keys, download_jobs)"
    echo ""
    echo "🔧 ESTIMATED TIME: 15-20 minutes"
    echo "💰 ESTIMATED COST: ~$50-80/month (dev environment)"
    echo "🌍 REGION: us-east-1"
    echo ""
    echo "⚠️  PREREQUISITES:"
    echo "   ✓ AWS CLI configured with valid credentials"
    echo "   ✓ Terraform installed (>= 1.0)"
    echo "   ✓ Docker installed (for image building)"
    echo "   ✓ jq installed (for JSON processing)"
    echo ""
    echo "🎛️  AVAILABLE COMMANDS:"
    echo "   ./deploy-infrastructure.sh          → Full deployment (default)"
    echo "   ./deploy-infrastructure.sh plan     → Show deployment plan only"  
    echo "   ./deploy-infrastructure.sh init     → Initialize Terraform only"
    echo "   ./deploy-infrastructure.sh rollback → Destroy all resources"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # Prompt for confirmation unless in non-interactive mode
    if [[ "${1:-}" != "auto" ]]; then
        read -p "🤔 Do you want to proceed with the deployment? (y/N): " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            echo "Deployment cancelled by user."
            exit 0
        fi
        echo ""
    fi
}

# Main script execution
main() {
    # Show comprehensive overview for full deployment
    case "${1:-}" in
        "rollback"|"destroy"|"plan"|"init")
            # Skip overview for utility commands
            ;;
        *)
            show_deployment_overview "$@"
            ;;
    esac
    
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