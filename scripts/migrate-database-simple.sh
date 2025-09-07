#!/bin/bash

# Simple Database Migration Script
# Uses the application's health check to verify database and table existence

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
MIGRATION_LOG="/tmp/database-migration.log"

# Utility functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$MIGRATION_LOG"
}

success() {
    echo -e "${GREEN}✅ $1${NC}" | tee -a "$MIGRATION_LOG"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}" | tee -a "$MIGRATION_LOG"
}

error() {
    echo -e "${RED}❌ $1${NC}" | tee -a "$MIGRATION_LOG"
}

# Get ALB endpoint from terraform
get_alb_endpoint() {
    if [ -f "$TERRAFORM_DIR/terraform.tfstate" ]; then
        cd "$TERRAFORM_DIR"
        terraform output -raw alb_endpoint 2>/dev/null || echo ""
    else
        echo ""
    fi
}

# Test database using application health check
test_database_via_health_check() {
    log "🔍 Testing database connectivity via application health check..."
    
    local alb_endpoint=$(get_alb_endpoint)
    if [[ -z "$alb_endpoint" ]]; then
        error "Could not get ALB endpoint from terraform outputs"
        return 1
    fi
    
    log "Checking health endpoint: $alb_endpoint/health/detailed"
    
    # Test basic connectivity first
    local health_response=$(curl -s "$alb_endpoint/health" 2>/dev/null || echo "failed")
    if [[ "$health_response" != *"healthy"* ]]; then
        error "Application health check failed: $health_response"
        return 1
    fi
    
    # Get detailed database information
    local detailed_response=$(curl -s "$alb_endpoint/health/detailed" 2>/dev/null || echo "failed")
    local db_status=$(echo "$detailed_response" | jq -r '.checks.database.status' 2>/dev/null || echo "unknown")
    
    if [[ "$db_status" == "healthy" ]]; then
        success "Database connectivity test passed"
        local db_version=$(echo "$detailed_response" | jq -r '.checks.database.version' 2>/dev/null || echo "unknown")
        log "Database version: $db_version"
        return 0
    else
        error "Database connectivity test failed - status: $db_status"
        return 1
    fi
}

# Check if migration is already running
check_running_migrations() {
    local cluster_name="$1"
    
    # Check for running migration tasks
    local running_tasks=$(aws ecs list-tasks \
        --cluster "$cluster_name" \
        --query 'taskArns[?contains(@, `youtube-downloader-dev-app`)]' \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$running_tasks" ]]; then
        for task_arn in $running_tasks; do
            local overrides=$(aws ecs describe-tasks \
                --cluster "$cluster_name" \
                --tasks "$task_arn" \
                --query 'tasks[0].overrides.containerOverrides[0].command' \
                --output text 2>/dev/null || echo "")
            
            if [[ "$overrides" == *"alembic"* && "$overrides" == *"upgrade"* ]]; then
                log "⚠️ Found running Alembic migration task: $task_arn"
                return 0  # Migration is already running
            fi
        done
    fi
    
    return 1  # No migration running
}

# Try to run Alembic migration via ECS
run_alembic_migration() {
    log "🔄 Attempting Alembic migration via ECS..."
    
    # Get ECS cluster name from terraform
    local cluster_name=""
    if [ -f "$TERRAFORM_DIR/terraform.tfstate" ]; then
        cd "$TERRAFORM_DIR"
        cluster_name=$(terraform output -json ecs_cluster_name 2>/dev/null | jq -r '.' || echo "")
    fi
    
    if [[ -z "$cluster_name" ]]; then
        warning "Could not get ECS cluster name from terraform - skipping Alembic migration"
        return 1
    fi
    
    log "Using ECS cluster: $cluster_name"
    
    # Check if migration is already running
    if check_running_migrations "$cluster_name"; then
        warning "Alembic migration is already running - skipping duplicate migration"
        log "Waiting for existing migration to complete..."
        sleep 30
        return 0
    fi
    
    # Run Alembic upgrade
    local task_arn=$(aws ecs run-task \
        --cluster "$cluster_name" \
        --task-definition "youtube-downloader-dev-app" \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[subnet-091fbb053364099db,subnet-06e58aa38a966b2bb],securityGroups=[sg-0a6949d40ea093478],assignPublicIp=ENABLED}" \
        --overrides '{"containerOverrides":[{"name":"fastapi-app","command":["alembic","upgrade","head"]}]}' \
        --query 'tasks[0].taskArn' \
        --output text 2>/dev/null || echo "FAILED")
    
    if [[ "$task_arn" == "FAILED" || "$task_arn" == "None" || -z "$task_arn" ]]; then
        warning "Could not start Alembic migration task"
        return 1
    fi
    
    log "Alembic migration task started: $task_arn"
    log "Waiting for migration to complete..."
    
    # Wait for task completion (timeout after 5 minutes)
    aws ecs wait tasks-stopped --cluster "$cluster_name" --tasks "$task_arn" --cli-read-timeout 300 || {
        warning "Alembic migration task timeout"
        return 1
    }
    
    # Check exit code
    local exit_code=$(aws ecs describe-tasks \
        --cluster "$cluster_name" \
        --tasks "$task_arn" \
        --query 'tasks[0].containers[0].exitCode' \
        --output text 2>/dev/null || echo "1")
    
    if [[ "$exit_code" == "0" ]]; then
        success "Alembic migration completed successfully"
        return 0
    else
        warning "Alembic migration failed (exit code: $exit_code)"
        return 1
    fi
}

# Check if tables are accessible via application
verify_tables_via_application() {
    log "🔍 Verifying database tables via application..."
    
    local alb_endpoint=$(get_alb_endpoint)
    if [[ -z "$alb_endpoint" ]]; then
        error "Could not get ALB endpoint for verification"
        return 1
    fi
    
    # The application's detailed health check will fail if tables don't exist
    local detailed_response=$(curl -s "$alb_endpoint/health/detailed" 2>/dev/null || echo "failed")
    local db_connected=$(echo "$detailed_response" | jq -r '.checks.database.connected' 2>/dev/null || echo "false")
    local db_status=$(echo "$detailed_response" | jq -r '.checks.database.status' 2>/dev/null || echo "unknown")
    
    if [[ "$db_connected" == "true" && "$db_status" == "healthy" ]]; then
        success "Database tables are accessible via application"
        
        # Extract database info
        local db_url=$(echo "$detailed_response" | jq -r '.checks.database.database_url' 2>/dev/null || echo "unknown")
        log "Database URL: $db_url"
        
        return 0
    else
        warning "Database tables may not be properly set up - application reports: connected=$db_connected, status=$db_status"
        return 1
    fi
}

# Main migration function
main() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "🗄️  SIMPLE DATABASE MIGRATION"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Clear previous migration log
    echo "Starting database migration at $(date)" > "$MIGRATION_LOG"
    
    # Step 1: Test database connectivity via application
    if ! test_database_via_health_check; then
        error "Database connectivity test failed - cannot proceed"
        return 1
    fi
    
    # Step 2: Check if tables already exist before running migration
    if verify_tables_via_application; then
        success "🎉 Database tables already exist and are accessible"
        success "   No migration needed - application can connect to database and access tables"
        return 0
    fi
    
    log "Database tables not found or not accessible - proceeding with migration..."
    
    # Step 3: Try Alembic migration
    if run_alembic_migration; then
        success "Migration completed via Alembic"
    else
        log "Alembic migration failed - checking if tables now exist..."
    fi
    
    # Step 4: Final verification after migration attempt
    if verify_tables_via_application; then
        success "🎉 Database migration completed successfully"
        success "   Application can connect to database and access tables"
        return 0
    else
        error "Database tables are still not properly accessible after migration attempt"
        log "📋 Manual investigation may be required:"
        log "   1. Check application logs for database errors"
        log "   2. Verify DATABASE_URL environment variable"
        log "   3. Check PostgreSQL database directly"
        log "   4. Check ECS task logs: aws logs tail /ecs/youtube-downloader-dev-app --follow"
        return 1
    fi
}

# Check prerequisites
if ! command -v aws &> /dev/null; then
    error "AWS CLI is not installed"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    error "jq is not installed"
    exit 1
fi

if ! command -v curl &> /dev/null; then
    error "curl is not installed"
    exit 1
fi

# Run main function
main "$@"