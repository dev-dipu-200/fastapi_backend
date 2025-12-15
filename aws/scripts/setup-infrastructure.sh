#!/bin/bash

# AWS Infrastructure Setup Script for Short URL Application
# This script sets up the necessary AWS infrastructure for deploying the application

set -e

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
PROJECT_NAME="shorturl"
VPC_CIDR="10.0.0.0/16"
SUBNET1_CIDR="10.0.1.0/24"
SUBNET2_CIDR="10.0.2.0/24"

echo "Setting up AWS infrastructure for $PROJECT_NAME in region $AWS_REGION..."

# Create ECR Repository
echo "Creating ECR repository..."
aws ecr create-repository \
    --repository-name ${PROJECT_NAME}-app \
    --region $AWS_REGION \
    --image-scanning-configuration scanOnPush=true \
    --encryption-configuration encryptionType=AES256 || echo "ECR repository already exists"

# Create CloudWatch Log Groups
echo "Creating CloudWatch log groups..."
aws logs create-log-group --log-group-name /ecs/${PROJECT_NAME}-app --region $AWS_REGION || echo "Log group already exists"
aws logs create-log-group --log-group-name /ecs/${PROJECT_NAME}-celery-worker --region $AWS_REGION || echo "Log group already exists"
aws logs create-log-group --log-group-name /ecs/${PROJECT_NAME}-celery-beat --region $AWS_REGION || echo "Log group already exists"

# Set log retention to 7 days
aws logs put-retention-policy --log-group-name /ecs/${PROJECT_NAME}-app --retention-in-days 7 --region $AWS_REGION
aws logs put-retention-policy --log-group-name /ecs/${PROJECT_NAME}-celery-worker --retention-in-days 7 --region $AWS_REGION
aws logs put-retention-policy --log-group-name /ecs/${PROJECT_NAME}-celery-beat --retention-in-days 7 --region $AWS_REGION

# Create VPC
echo "Creating VPC..."
VPC_ID=$(aws ec2 create-vpc \
    --cidr-block $VPC_CIDR \
    --region $AWS_REGION \
    --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=${PROJECT_NAME}-vpc}]" \
    --query 'Vpc.VpcId' \
    --output text) || echo "VPC creation failed"

echo "VPC ID: $VPC_ID"

# Enable DNS hostnames
aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames

# Create Internet Gateway
echo "Creating Internet Gateway..."
IGW_ID=$(aws ec2 create-internet-gateway \
    --region $AWS_REGION \
    --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=${PROJECT_NAME}-igw}]" \
    --query 'InternetGateway.InternetGatewayId' \
    --output text)

aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID --region $AWS_REGION

# Create Subnets
echo "Creating subnets..."
SUBNET1_ID=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block $SUBNET1_CIDR \
    --availability-zone ${AWS_REGION}a \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=${PROJECT_NAME}-subnet1}]" \
    --query 'Subnet.SubnetId' \
    --output text)

SUBNET2_ID=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block $SUBNET2_CIDR \
    --availability-zone ${AWS_REGION}b \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=${PROJECT_NAME}-subnet2}]" \
    --query 'Subnet.SubnetId' \
    --output text)

echo "Subnet 1 ID: $SUBNET1_ID"
echo "Subnet 2 ID: $SUBNET2_ID"

# Create Route Table
echo "Creating route table..."
ROUTE_TABLE_ID=$(aws ec2 create-route-table \
    --vpc-id $VPC_ID \
    --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=${PROJECT_NAME}-rt}]" \
    --query 'RouteTable.RouteTableId' \
    --output text)

# Create route to Internet Gateway
aws ec2 create-route \
    --route-table-id $ROUTE_TABLE_ID \
    --destination-cidr-block 0.0.0.0/0 \
    --gateway-id $IGW_ID

# Associate route table with subnets
aws ec2 associate-route-table --subnet-id $SUBNET1_ID --route-table-id $ROUTE_TABLE_ID
aws ec2 associate-route-table --subnet-id $SUBNET2_ID --route-table-id $ROUTE_TABLE_ID

# Create Security Group
echo "Creating security group..."
SG_ID=$(aws ec2 create-security-group \
    --group-name ${PROJECT_NAME}-sg \
    --description "Security group for ${PROJECT_NAME} application" \
    --vpc-id $VPC_ID \
    --query 'GroupId' \
    --output text)

# Add inbound rules
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 8000 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 443 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 5432 --source-group $SG_ID
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 27017 --source-group $SG_ID
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 6379 --source-group $SG_ID
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 5672 --source-group $SG_ID

echo "Security Group ID: $SG_ID"

# Create ECS Cluster
echo "Creating ECS cluster..."
aws ecs create-cluster \
    --cluster-name ${PROJECT_NAME}-cluster \
    --region $AWS_REGION \
    --capacity-providers FARGATE FARGATE_SPOT \
    --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1 || echo "Cluster already exists"

# Create Application Load Balancer
echo "Creating Application Load Balancer..."
ALB_ARN=$(aws elbv2 create-load-balancer \
    --name ${PROJECT_NAME}-alb \
    --subnets $SUBNET1_ID $SUBNET2_ID \
    --security-groups $SG_ID \
    --scheme internet-facing \
    --type application \
    --ip-address-type ipv4 \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text)

echo "ALB ARN: $ALB_ARN"

# Create Target Group
echo "Creating target group..."
TG_ARN=$(aws elbv2 create-target-group \
    --name ${PROJECT_NAME}-tg \
    --protocol HTTP \
    --port 8000 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path /api/ \
    --health-check-interval-seconds 30 \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text)

echo "Target Group ARN: $TG_ARN"

# Create Listener
echo "Creating ALB listener..."
aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn=$TG_ARN

echo ""
echo "Infrastructure setup complete!"
echo ""
echo "Please save these values:"
echo "VPC_ID: $VPC_ID"
echo "SUBNET1_ID: $SUBNET1_ID"
echo "SUBNET2_ID: $SUBNET2_ID"
echo "SECURITY_GROUP_ID: $SG_ID"
echo "ALB_ARN: $ALB_ARN"
echo "TARGET_GROUP_ARN: $TG_ARN"
echo ""
echo "Next steps:"
echo "1. Set up RDS PostgreSQL database"
echo "2. Set up DocumentDB (MongoDB) or MongoDB Atlas"
echo "3. Set up ElastiCache Redis"
echo "4. Set up Amazon MQ (RabbitMQ)"
echo "5. Store secrets in AWS Secrets Manager"
echo "6. Update task-definition.json with actual values"
echo "7. Register ECS task definition"
echo "8. Create ECS service"
