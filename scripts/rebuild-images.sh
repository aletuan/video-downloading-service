#!/bin/bash

# Script to rebuild Docker images for correct architecture (x86_64/amd64)
# This fixes the "exec format error" issue with ECS Fargate

echo "Rebuilding Docker images for x86_64 architecture..."

# Navigate to project root
cd /Users/andy/Workspace/Claude/video-downloading-service

# Login to ECR
echo "Logging into ECR..."
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 575108929177.dkr.ecr.us-east-1.amazonaws.com

# Build FastAPI app image for x86_64
echo "Building FastAPI app image for x86_64..."
docker build --platform linux/amd64 -t 575108929177.dkr.ecr.us-east-1.amazonaws.com/youtube-downloader/app:latest -f Dockerfile .

# Build Celery worker image for x86_64
echo "Building Celery worker image for x86_64..."
docker build --platform linux/amd64 -t 575108929177.dkr.ecr.us-east-1.amazonaws.com/youtube-downloader/worker:latest -f Dockerfile.worker .

# Push both images
echo "Pushing images to ECR..."
docker push 575108929177.dkr.ecr.us-east-1.amazonaws.com/youtube-downloader/app:latest
docker push 575108929177.dkr.ecr.us-east-1.amazonaws.com/youtube-downloader/worker:latest

echo "Done! Images rebuilt for correct architecture and pushed to ECR."
echo "Next step: Force new ECS deployment to use updated images"
echo "Run: aws ecs update-service --cluster youtube-downloader-dev-cluster-0ca94b2c --service youtube-downloader-dev-app --force-new-deployment"
echo "Run: aws ecs update-service --cluster youtube-downloader-dev-cluster-0ca94b2c --service youtube-downloader-dev-worker --force-new-deployment"