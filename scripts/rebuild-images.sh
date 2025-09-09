#!/bin/bash

# Script to rebuild Docker images for correct architecture (x86_64/amd64)
# This fixes the "exec format error" issue with ECS Fargate

echo "Rebuilding Docker images for x86_64 architecture..."

# Navigate to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

# Configuration
TERRAFORM_DIR="${PROJECT_ROOT}/infrastructure/terraform/environments/dev"

# Function to get terraform outputs
get_terraform_output() {
    local output_name=$1
    local default_value=${2:-""}
    
    if [ -d "$TERRAFORM_DIR" ]; then
        cd "$TERRAFORM_DIR"
        local value=$(terraform output -raw "$output_name" 2>/dev/null || echo "$default_value")
        cd "$PROJECT_ROOT"
        echo "$value"
    else
        echo "$default_value"
    fi
}

# Get dynamic values from terraform
ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "575108929177")
AWS_REGION=$(get_terraform_output "region" "us-east-1")
CLUSTER_NAME=$(get_terraform_output "ecs_cluster_name")
APP_SERVICE_NAME=$(get_terraform_output "app_service_name")
WORKER_SERVICE_NAME=$(get_terraform_output "worker_service_name")

# Login to ECR
echo "Logging into ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${ECR_REGISTRY}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Build FastAPI app image for x86_64
echo "Building FastAPI app image for x86_64..."
docker build --platform linux/amd64 -t "${ECR_REGISTRY}.dkr.ecr.${AWS_REGION}.amazonaws.com/youtube-downloader/app:latest" -f Dockerfile .

# Build Celery worker image for x86_64
echo "Building Celery worker image for x86_64..."
docker build --platform linux/amd64 -t "${ECR_REGISTRY}.dkr.ecr.${AWS_REGION}.amazonaws.com/youtube-downloader/worker:latest" -f Dockerfile.worker .

# Push both images
echo "Pushing images to ECR..."
docker push "${ECR_REGISTRY}.dkr.ecr.${AWS_REGION}.amazonaws.com/youtube-downloader/app:latest"
docker push "${ECR_REGISTRY}.dkr.ecr.${AWS_REGION}.amazonaws.com/youtube-downloader/worker:latest"

echo "Images rebuilt for correct architecture and pushed to ECR successfully."
echo "Next step: Force new ECS deployment to use updated images"

if [[ -n "$CLUSTER_NAME" && -n "$APP_SERVICE_NAME" && -n "$WORKER_SERVICE_NAME" ]]; then
    echo "Run: aws ecs update-service --cluster $CLUSTER_NAME --service $APP_SERVICE_NAME --force-new-deployment"
    echo "Run: aws ecs update-service --cluster $CLUSTER_NAME --service $WORKER_SERVICE_NAME --force-new-deployment"
else
    echo "Could not extract cluster/service names from terraform outputs."
    echo "You may need to run the deployment script or check terraform outputs manually."
fi