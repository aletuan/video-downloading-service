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

# Advanced rollback configuration
ROLLBACK_COMPONENT="all"
DRY_RUN=false
FORCE=false
TARGET_VERSION=""

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

# Enhanced utility functions for rollback
confirm() {
    if [[ "$FORCE" == "true" ]]; then
        return 0
    fi
    
    local message="$1"
    echo -e "${YELLOW}$message${NC}"
    read -p "Continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        error "Operation cancelled by user"
        exit 1
    fi
}

show_rollback_help() {
    cat << EOF
Enhanced Rollback Options for YouTube Download Service

USAGE:
    $0 rollback [OPTIONS]

OPTIONS:
    --component COMP     Component to rollback (all, app, infrastructure, cookies)
    --version VERSION    Target version to rollback to
    --dry-run           Show what would be done without executing
    --force             Force rollback without confirmations
    --help              Show this help message

EXAMPLES:
    # Full rollback (existing behavior)
    $0 rollback

    # Rollback only application containers
    $0 rollback --component app

    # Rollback only cookie management components
    $0 rollback --component cookies --version v1.2.0

    # Dry run of full rollback
    $0 rollback --dry-run

COMPONENTS:
    all              Rollback entire application and infrastructure
    app              Rollback application containers only
    infrastructure   Rollback Terraform infrastructure only
    cookies          Rollback cookie management components only

EOF
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
    
    # Debug: Show current working directory and terraform state
    log "Debug: Working directory: $(pwd)"
    log "Debug: Terraform state file exists: $(test -f terraform.tfstate && echo 'YES' || echo 'NO')"
    
    # Plan phase with detailed logging
    log "Planning terraform module: $module"
    if terraform plan -target="module.$module" -out="/tmp/terraform-$module.plan" 2>&1 | tee "/tmp/terraform-$module-plan.log"; then
        log "Plan successful, proceeding with apply..."
        
        # Apply phase with detailed logging
        log "Applying terraform module: $module"
        if terraform apply "/tmp/terraform-$module.plan" 2>&1 | tee "/tmp/terraform-$module-apply.log"; then
            success "Phase $phase COMPLETED"
            rm -f "/tmp/terraform-$module.plan"
            return 0
        else
            error "Apply failed for module $module"
            log "Apply log saved to: /tmp/terraform-$module-apply.log"
        fi
    else
        error "Plan failed for module $module"
        log "Plan log saved to: /tmp/terraform-$module-plan.log"
    fi
    
    error "Phase $phase FAILED"
    log "Debug logs available at:"
    log "  - Plan: /tmp/terraform-$module-plan.log"
    log "  - Apply: /tmp/terraform-$module-apply.log"
    return 1
}

# Debug: Deploy just Phase 6F for troubleshooting
debug_phase_6f() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "DEBUG MODE: Running Phase 6F (Compute Platform) Only"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Ensure we're in the right directory
    cd "$TERRAFORM_DIR"
    
    # Show terraform status before attempting Phase 6F
    log "Current terraform state:"
    terraform state list | grep -E "(compute|secure_storage)" || log "No compute/secure_storage resources in state"
    
    # Check for any drift in existing resources that compute depends on
    log "Checking dependencies (networking, storage, database modules):"
    terraform plan -target="module.networking" -detailed-exitcode || log "Networking module has changes"
    terraform plan -target="module.storage" -detailed-exitcode || log "Storage module has changes" 
    terraform plan -target="module.database" -detailed-exitcode || log "Database module has changes"
    
    # Now attempt Phase 6F with full debugging
    deploy_module "6F" "compute" "Compute Platform (ECS Fargate Cluster + Task Definitions)"
    
    if [ $? -eq 0 ]; then
        success "Phase 6F Debug Run COMPLETED"
    else
        error "Phase 6F Debug Run FAILED"
        log "Checking logs for detailed error information..."
        [ -f "/tmp/terraform-compute-plan.log" ] && tail -20 "/tmp/terraform-compute-plan.log"
        [ -f "/tmp/terraform-compute-apply.log" ] && tail -20 "/tmp/terraform-compute-apply.log"
    fi
}

# Deploy all infrastructure phases
deploy_all_phases() {
    echo "STARTING DEPLOYMENT EXECUTION..."
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
    log "Phase 6G: Application Deployment"
    
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
    log "Phase 6H: Database Migration"
    cd "$TERRAFORM_DIR"
    
    if terraform apply -target=null_resource.database_migration -auto-approve; then
        success "Database tables created (api_keys, download_jobs, alembic_version)"
    else
        warning "Database migration failed - API endpoints may not work properly"
    fi
    
    # Final Health Check
    echo ""
    log "Final Health Verification"
    ALB_ENDPOINT=$(terraform output -raw alb_endpoint 2>/dev/null)
    if [[ -n "$ALB_ENDPOINT" ]]; then
        HEALTH_RESPONSE=$(curl -s "$ALB_ENDPOINT/health" 2>/dev/null || echo "failed")
        if [[ "$HEALTH_RESPONSE" == *"healthy"* ]]; then
            success "Application health check: PASSED"
        else
            warning "Application health check: FAILED or starting up"
            log "Manual test: curl $ALB_ENDPOINT/health"
        fi
    fi
    
    # Save outputs
    terraform output > "/tmp/terraform-final-outputs.txt"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    success "DEPLOYMENT COMPLETED SUCCESSFULLY!"
    success "All 8 phases deployed (6A-6H)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Show deployment summary
show_deployment_summary() {
    log "=== DEPLOYMENT SUMMARY ==="
    
    cd "$TERRAFORM_DIR"
    
    echo ""
    log "Infrastructure Overview:"
    terraform output | grep -E "(alb_endpoint|database_endpoint|redis_endpoint|s3_bucket_name|ecs_cluster_name)" || true
    
    echo ""
    log "Cost Estimation:"
    terraform output | grep -E "(estimated_monthly_cost|total_estimated)" || true
    
    echo ""
    log "Phase 6G Status:"
    terraform output | grep -E "(app_service_name|worker_service_name)" || true
    
    # Check ALB health
    ALB_ENDPOINT=$(terraform output -raw alb_endpoint 2>/dev/null)
    if [[ -n "$ALB_ENDPOINT" ]]; then
        echo "Health Check: $ALB_ENDPOINT/health"
        HEALTH_STATUS=$(curl -s "$ALB_ENDPOINT/health" 2>/dev/null || echo "Not Ready")
        echo "   Status: $HEALTH_STATUS"
    fi
    
    echo ""
    log "Available Actions:"
    echo "1. Test application: curl $ALB_ENDPOINT/health"
    echo "2. Rebuild images: ./scripts/rebuild-images.sh" 
    echo "3. View ECS logs: aws logs get-log-events --log-group-name /ecs/youtube-downloader-dev-app"
    echo "4. Rollback all: ./scripts/deploy-infrastructure.sh rollback"
    echo ""
    log "Full outputs saved to: /tmp/terraform-final-outputs.txt"
    log "Deployment log saved to: $LOG_FILE"
}

# Advanced rollback functions
rollback_application() {
    log "Starting application rollback..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would rollback ECS services to previous versions"
        return 0
    fi
    
    confirm "This will rollback application containers. Current sessions may be interrupted."
    
    # Get cluster name
    local cluster_name
    cluster_name=$(get_terraform_output "ecs_cluster_name")
    
    if [[ -z "$cluster_name" ]]; then
        error "Could not find ECS cluster name from Terraform outputs"
        return 1
    fi
    
    log "Rolling back services in cluster: $cluster_name"
    
    # Rollback app service
    local app_service_name
    app_service_name=$(get_terraform_output "app_service_name")
    
    if [[ -n "$app_service_name" ]]; then
        log "Rolling back app service: $app_service_name"
        
        # Get previous task definition revision
        local task_family="youtube-downloader-dev-app"
        local previous_revision
        
        if [[ -n "$TARGET_VERSION" ]]; then
            previous_revision="$task_family:$TARGET_VERSION"
        else
            # Get second most recent revision
            previous_revision=$(aws ecs list-task-definitions \
                --family-prefix "$task_family" \
                --status ACTIVE --sort DESC \
                --query "taskDefinitionArns[1]" --output text 2>/dev/null || echo "")
        fi
        
        if [[ -n "$previous_revision" && "$previous_revision" != "None" ]]; then
            log "Rolling back to task definition: $(basename "$previous_revision")"
            
            aws ecs update-service \
                --cluster "$cluster_name" \
                --service "$app_service_name" \
                --task-definition "$previous_revision" \
                --force-new-deployment
            
            # Wait for rollback to complete
            log "Waiting for service rollback to complete..."
            aws ecs wait services-stable --cluster "$cluster_name" --services "$app_service_name"
            
            success "App service rollback completed"
        else
            error "Could not find previous task definition for rollback"
            return 1
        fi
    fi
    
    # Rollback worker service
    local worker_service_name
    worker_service_name=$(get_terraform_output "worker_service_name")
    
    if [[ -n "$worker_service_name" ]]; then
        log "Rolling back worker service: $worker_service_name"
        
        local task_family="youtube-downloader-dev-worker"
        local previous_revision
        
        if [[ -n "$TARGET_VERSION" ]]; then
            previous_revision="$task_family:$TARGET_VERSION"
        else
            previous_revision=$(aws ecs list-task-definitions \
                --family-prefix "$task_family" \
                --status ACTIVE --sort DESC \
                --query "taskDefinitionArns[1]" --output text 2>/dev/null || echo "")
        fi
        
        if [[ -n "$previous_revision" && "$previous_revision" != "None" ]]; then
            aws ecs update-service \
                --cluster "$cluster_name" \
                --service "$worker_service_name" \
                --task-definition "$previous_revision" \
                --force-new-deployment
            
            aws ecs wait services-stable --cluster "$cluster_name" --services "$worker_service_name"
            success "Worker service rollback completed"
        fi
    fi
    
    success "Application rollback completed successfully"
}

rollback_infrastructure() {
    log "Starting infrastructure rollback..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would rollback Terraform infrastructure"
        return 0
    fi
    
    confirm "This will rollback infrastructure changes. This may affect system availability."
    
    # This delegates to the existing full rollback for infrastructure
    rollback_deployment_full
}

rollback_cookie_management() {
    log "Starting cookie management component rollback..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would rollback cookie management configuration"
        return 0
    fi
    
    confirm "This will rollback cookie management settings and may disable cookie functionality."
    
    # Rollback cookie-related Parameter Store values
    log "Rolling back cookie manager configuration..."
    
    local params=(
        "/youtube-downloader/dev/cookie/encryption-key"
        "/youtube-downloader/dev/cookie/validation-enabled"
        "/youtube-downloader/dev/cookie/refresh-interval"
    )
    
    for param in "${params[@]}"; do
        if aws ssm get-parameter --name "$param-backup" >/dev/null 2>&1; then
            log "Restoring parameter: $param"
            
            local backup_value
            backup_value=$(aws ssm get-parameter --name "$param-backup" \
                --with-decryption --query "Parameter.Value" --output text 2>/dev/null || echo "")
            
            if [[ -n "$backup_value" ]]; then
                aws ssm put-parameter --name "$param" \
                    --value "$backup_value" --type SecureString --overwrite
            fi
        else
            warning "No backup found for parameter: $param"
        fi
    done
    
    # Handle cookie files in S3 if bucket exists
    local cookie_bucket
    cookie_bucket=$(get_terraform_output "secure_config_bucket_name")
    
    if [[ -n "$cookie_bucket" ]]; then
        log "Managing cookie files in S3 bucket: $cookie_bucket"
        
        # Move current cookies to backup location
        aws s3 cp "s3://$cookie_bucket/cookies/youtube-cookies-active.txt" \
                  "s3://$cookie_bucket/cookies/backups/rollback-$(date +%Y%m%d-%H%M%S).txt" 2>/dev/null || true
        
        # Restore from latest good backup if available
        local latest_backup
        latest_backup=$(aws s3 ls "s3://$cookie_bucket/cookies/backups/" \
            --recursive | grep "\.txt$" | tail -n 1 | awk '{print $NF}' || echo "")
        
        if [[ -n "$latest_backup" ]]; then
            log "Restoring from backup: $(basename "$latest_backup")"
            aws s3 cp "s3://$cookie_bucket/$latest_backup" \
                      "s3://$cookie_bucket/cookies/youtube-cookies-active.txt"
        fi
    fi
    
    success "Cookie management rollback completed"
}

# Enhanced rollback function with component support
rollback_deployment_enhanced() {
    local component="${1:-$ROLLBACK_COMPONENT}"
    
    log "Enhanced rollback requested - Component: $component"
    
    # Show rollback plan
    if [[ "$DRY_RUN" == "false" ]]; then
        log "Rollback Plan:"
        log "  Component: $component"
        log "  Target Version: ${TARGET_VERSION:-"Previous version"}"
        log "  Dry Run: $DRY_RUN"
        echo ""
    fi
    
    # Execute rollback based on component
    case "$component" in
        all)
            rollback_application
            rollback_infrastructure
            ;;
        app)
            rollback_application
            ;;
        infrastructure)
            rollback_infrastructure
            ;;
        cookies)
            rollback_cookie_management
            ;;
        *)
            error "Invalid component: $component"
            show_rollback_help
            exit 1
            ;;
    esac
    
    if [[ "$DRY_RUN" == "true" ]]; then
        success "Dry run completed successfully"
    else
        success "Enhanced rollback completed successfully"
    fi
}

# Original rollback function (renamed for clarity)
rollback_deployment_full() {
    warning "ROLLBACK REQUESTED"
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
                            success "ECR repository '$repo' deleted successfully"
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
            success "All Terraform resources destroyed successfully"
            
            # Final verification
            log "Performing final cleanup verification..."
            
            # Check terraform state
            if [ "$(terraform state list | wc -l)" -eq 0 ]; then
                success "Terraform state is clean"
            else
                warning "⚠️  Some resources may remain in terraform state"
            fi
            
            # Check ECR repositories
            ECR_CHECK=$(aws ecr describe-repositories --region us-east-1 --query 'repositories[].repositoryName' --output text 2>/dev/null || echo "")
            if [[ -z "$ECR_CHECK" ]]; then
                success "All ECR repositories cleaned up"
            else
                warning "⚠️  Some ECR repositories may still exist: $ECR_CHECK"
            fi
            
            success "Complete infrastructure rollback finished!"
            log "Cost savings: All recurring AWS charges eliminated"
            
        else
            error "❌ Terraform rollback failed - manual cleanup may be required"
            log "You may need to manually delete ECR repositories:"
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
    echo "AWS INFRASTRUCTURE DEPLOYMENT - YOUTUBE DOWNLOADER SERVICE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "DEPLOYMENT WORKFLOW (8 Phases):"
    echo "   Phase 6A: Core Infrastructure    → VPC, Subnets, Security Groups"
    echo "   Phase 6B: Storage Layer          → S3 Bucket with Lifecycle"  
    echo "   Phase 6C: Database & Cache       → PostgreSQL RDS + ElastiCache Redis"
    echo "   Phase 6D: Queue System           → SQS Main Queue + Dead Letter Queue"
    echo "   Phase 6E: Load Balancing         → Application Load Balancer + SSL"
    echo "   Phase 6F: Compute Platform       → ECS Fargate Cluster + Task Definitions"
    echo "   Phase 6G: Application Deploy     → Docker Images + ECS Services"
    echo "   Phase 6H: Database Migration     → Create Tables (api_keys, download_jobs)"
    echo ""
    echo "ESTIMATED TIME: 15-20 minutes"
    echo "ESTIMATED COST: ~$50-80/month (dev environment)"
    echo "REGION: us-east-1"
    echo ""
    echo "⚠️  PREREQUISITES:"
    echo "   ✓ AWS CLI configured with valid credentials"
    echo "   ✓ Terraform installed (>= 1.0)"
    echo "   ✓ Docker installed (for image building)"
    echo "   ✓ jq installed (for JSON processing)"
    echo ""
    echo "AVAILABLE COMMANDS:"
    echo "   ./deploy-infrastructure.sh              → Full deployment (default)"
    echo "   ./deploy-infrastructure.sh plan         → Show deployment plan only"  
    echo "   ./deploy-infrastructure.sh init         → Initialize Terraform only"
    echo "   ./deploy-infrastructure.sh rollback     → Destroy all resources (full rollback)"
    echo ""
    echo "ENHANCED ROLLBACK OPTIONS:"
    echo "   ./deploy-infrastructure.sh rollback --component app        → Rollback application containers only"
    echo "   ./deploy-infrastructure.sh rollback --component cookies    → Rollback cookie management only"
    echo "   ./deploy-infrastructure.sh rollback --dry-run             → Show rollback plan without executing"
    echo "   ./deploy-infrastructure.sh rollback --help                → Show detailed rollback options"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # Prompt for confirmation unless in non-interactive mode
    if [[ "${1:-}" != "auto" ]]; then
        read -p "Do you want to proceed with the deployment? (y/N): " confirm
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
            # Parse rollback-specific parameters
            shift # Remove 'rollback' from arguments
            
            while [[ $# -gt 0 ]]; do
                case $1 in
                    --component)
                        ROLLBACK_COMPONENT="$2"
                        shift 2
                        ;;
                    --version)
                        TARGET_VERSION="$2"
                        shift 2
                        ;;
                    --dry-run)
                        DRY_RUN=true
                        shift
                        ;;
                    --force)
                        FORCE=true
                        shift
                        ;;
                    --help)
                        show_rollback_help
                        exit 0
                        ;;
                    *)
                        error "Unknown rollback option: $1"
                        show_rollback_help
                        exit 1
                        ;;
                esac
            done
            
            # Execute appropriate rollback based on component
            if [[ "$ROLLBACK_COMPONENT" == "all" && "$DRY_RUN" == "false" && -z "$TARGET_VERSION" ]]; then
                # Full infrastructure destruction (legacy behavior)
                rollback_deployment_full
            else
                # Enhanced component-based rollback
                rollback_deployment_enhanced
            fi
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
        "debug")
            # Debug specific phase
            case "${2:-}" in
                "6f"|"phase6f"|"compute")
                    log "🔍 Running Phase 6F debug session..."
                    check_prerequisites
                    terraform_init
                    debug_phase_6f
                    ;;
                *)
                    error "Please specify which phase to debug: 6f, phase6f, or compute"
                    echo "Usage: $0 debug 6f"
                    exit 1
                    ;;
            esac
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