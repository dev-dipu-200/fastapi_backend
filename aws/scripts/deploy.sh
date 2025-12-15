#!/bin/bash

# Deployment script for Short URL Application to AWS ECS
set -e

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
ECR_REPOSITORY=${ECR_REPOSITORY:-shorturl-app}
ECS_CLUSTER=${ECS_CLUSTER:-shorturl-cluster}
ECS_SERVICE=${ECS_SERVICE:-shorturl-service}
ECS_TASK_DEFINITION=${ECS_TASK_DEFINITION:-shorturl-task}

# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Starting deployment process..."
echo "AWS Account ID: $AWS_ACCOUNT_ID"
echo "ECR Registry: $ECR_REGISTRY"
echo "Region: $AWS_REGION"

# Login to ECR
echo "Logging in to Amazon ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY

# Build Docker image
echo "Building Docker image..."
docker build -t $ECR_REPOSITORY:latest .

# Tag image
echo "Tagging image..."
docker tag $ECR_REPOSITORY:latest $ECR_REGISTRY/$ECR_REPOSITORY:latest
docker tag $ECR_REPOSITORY:latest $ECR_REGISTRY/$ECR_REPOSITORY:$(git rev-parse --short HEAD)

# Push to ECR
echo "Pushing image to ECR..."
docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest
docker push $ECR_REGISTRY/$ECR_REPOSITORY:$(git rev-parse --short HEAD)

# Update ECS service
echo "Updating ECS service..."
aws ecs update-service \
    --cluster $ECS_CLUSTER \
    --service $ECS_SERVICE \
    --force-new-deployment \
    --region $AWS_REGION

echo "Waiting for service to stabilize..."
aws ecs wait services-stable \
    --cluster $ECS_CLUSTER \
    --services $ECS_SERVICE \
    --region $AWS_REGION

echo "Deployment completed successfully!"

# Get service URL
ALB_DNS=$(aws elbv2 describe-load-balancers \
    --region $AWS_REGION \
    --query "LoadBalancers[?contains(LoadBalancerName, 'shorturl')].DNSName" \
    --output text)

echo ""
echo "Application is available at: http://$ALB_DNS"
