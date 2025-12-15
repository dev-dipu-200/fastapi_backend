# Deployment Guide

This guide covers deploying the Short URL FastAPI application using Docker and AWS ECS with a complete CI/CD pipeline.

## Table of Contents
- [Local Development with Docker](#local-development-with-docker)
- [AWS Deployment](#aws-deployment)
- [CI/CD Pipeline](#cicd-pipeline)
- [Monitoring and Logs](#monitoring-and-logs)
- [Troubleshooting](#troubleshooting)

## Local Development with Docker

### Prerequisites
- Docker and Docker Compose installed
- Git
- Python 3.12+ (for local development without Docker)

### Quick Start

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd Sort_Url
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start all services**
   ```bash
   docker-compose up -d
   ```

   This will start:
   - FastAPI application (port 8000)
   - PostgreSQL database (port 5432)
   - MongoDB (port 27017)
   - Redis (port 6379)
   - RabbitMQ (ports 5672, 15672)
   - Celery worker
   - Celery beat scheduler
   - Nginx reverse proxy (port 80)

4. **Access the application**
   - API: http://localhost/api/
   - RabbitMQ Management: http://localhost:15672 (guest/guest)

5. **View logs**
   ```bash
   # All services
   docker-compose logs -f

   # Specific service
   docker-compose logs -f app
   docker-compose logs -f celery_worker
   docker-compose logs -f celery_beat
   ```

6. **Stop services**
   ```bash
   docker-compose down

   # Remove volumes as well
   docker-compose down -v
   ```

### Development Commands

```bash
# Rebuild containers after code changes
docker-compose up -d --build

# Run database migrations
docker-compose exec app alembic upgrade head

# Access application shell
docker-compose exec app bash

# Run tests
docker-compose exec app pytest

# View Celery worker status
docker-compose exec celery_worker celery -A src.configure.celery:celery_app inspect active
```

## AWS Deployment

### Prerequisites
- AWS CLI configured with appropriate credentials
- AWS account with necessary permissions
- Domain name (optional, for SSL)

### Step 1: Set Up AWS Infrastructure

1. **Configure AWS credentials**
   ```bash
   aws configure
   ```

2. **Run infrastructure setup script**
   ```bash
   chmod +x aws/scripts/setup-infrastructure.sh
   ./aws/scripts/setup-infrastructure.sh
   ```

   This creates:
   - VPC with subnets
   - Security groups
   - ECR repository
   - ECS cluster
   - Application Load Balancer
   - CloudWatch log groups

3. **Note the output values** (VPC ID, subnet IDs, security group ID, etc.)

### Step 2: Set Up Managed Services

#### PostgreSQL (RDS)
```bash
aws rds create-db-instance \
    --db-instance-identifier shorturl-postgres \
    --db-instance-class db.t3.micro \
    --engine postgres \
    --engine-version 15.4 \
    --master-username admin \
    --master-user-password YOUR_PASSWORD \
    --allocated-storage 20 \
    --vpc-security-group-ids sg-xxxxx \
    --db-subnet-group-name your-subnet-group \
    --backup-retention-period 7 \
    --no-publicly-accessible
```

#### MongoDB (DocumentDB or Atlas)
Option 1: Amazon DocumentDB
```bash
aws docdb create-db-cluster \
    --db-cluster-identifier shorturl-docdb \
    --engine docdb \
    --master-username admin \
    --master-user-password YOUR_PASSWORD \
    --vpc-security-group-ids sg-xxxxx \
    --db-subnet-group-name your-subnet-group
```

Option 2: Use MongoDB Atlas (recommended for ease of use)

#### Redis (ElastiCache)
```bash
aws elasticache create-cache-cluster \
    --cache-cluster-id shorturl-redis \
    --engine redis \
    --cache-node-type cache.t3.micro \
    --num-cache-nodes 1 \
    --security-group-ids sg-xxxxx \
    --cache-subnet-group-name your-subnet-group
```

#### RabbitMQ (Amazon MQ)
```bash
aws mq create-broker \
    --broker-name shorturl-rabbitmq \
    --engine-type RABBITMQ \
    --engine-version 3.11 \
    --host-instance-type mq.t3.micro \
    --users Username=admin,Password=YOUR_PASSWORD \
    --subnet-ids subnet-xxxxx \
    --security-groups sg-xxxxx \
    --publicly-accessible false
```

### Step 3: Store Secrets

```bash
# Store application secrets
aws secretsmanager create-secret \
    --name shorturl/SECRET_KEY \
    --secret-string "your-secret-key"

aws secretsmanager create-secret \
    --name shorturl/OPENAI_API_KEY \
    --secret-string "your-openai-api-key"

# Add more secrets as needed
```

### Step 4: Update Task Definition

1. Edit `aws/task-definition.json`
2. Replace placeholders:
   - `YOUR_AWS_ACCOUNT_ID`
   - Database endpoints
   - Secret ARNs

### Step 5: Register Task Definition

```bash
aws ecs register-task-definition \
    --cli-input-json file://aws/task-definition.json
```

### Step 6: Create ECS Service

```bash
aws ecs create-service \
    --cluster shorturl-cluster \
    --service-name shorturl-service \
    --task-definition shorturl-task \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=shorturl-app,containerPort=8000"
```

### Step 7: Deploy Application

```bash
chmod +x aws/scripts/deploy.sh
./aws/scripts/deploy.sh
```

## CI/CD Pipeline

### GitHub Actions Setup

1. **Add GitHub Secrets**

   Go to your repository Settings → Secrets and variables → Actions, and add:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION` (optional, defaults to us-east-1)

2. **Workflow Triggers**

   The CI/CD pipeline runs on:
   - Push to `main` branch (runs tests, builds, and deploys)
   - Push to `develop` branch (runs tests only)
   - Pull requests to `main` or `develop` (runs tests only)

3. **Pipeline Stages**

   - **Test**: Runs unit tests with PostgreSQL, MongoDB, and Redis
   - **Build and Push**: Builds Docker image and pushes to ECR (main branch only)
   - **Deploy**: Updates ECS service with new image (main branch only)

### Manual Deployment

To manually trigger a deployment:

```bash
# Using GitHub CLI
gh workflow run ci-cd.yml

# Or push a tag
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

## Monitoring and Logs

### Application Logs

Logs are stored in multiple locations:

1. **Docker Compose (Local)**
   ```bash
   # View logs
   docker-compose logs -f app
   docker-compose logs -f celery_worker

   # Logs are also written to ./logs/ directory
   tail -f logs/app.log
   tail -f logs/error.log
   tail -f logs/celery.log
   ```

2. **AWS CloudWatch (Production)**
   ```bash
   # View logs
   aws logs tail /ecs/shorturl-app --follow
   aws logs tail /ecs/shorturl-celery-worker --follow
   aws logs tail /ecs/shorturl-celery-beat --follow
   ```

### Celery Monitoring

1. **Flower (Web-based)**

   Add to docker-compose.yml:
   ```yaml
   flower:
     build: .
     command: celery -A src.configure.celery:celery_app flower --port=5555
     ports:
       - "5555:5555"
     depends_on:
       - rabbitmq
   ```

2. **Celery CLI**
   ```bash
   # Check active tasks
   celery -A src.configure.celery:celery_app inspect active

   # Check registered tasks
   celery -A src.configure.celery:celery_app inspect registered

   # Check scheduled tasks
   celery -A src.configure.celery:celery_app inspect scheduled
   ```

### Health Checks

- **Application**: `http://your-domain/api/`
- **Nginx**: `http://your-domain/health`
- **RabbitMQ**: `http://your-domain:15672`

## Troubleshooting

### Common Issues

#### 1. Celery Worker Not Connecting to RabbitMQ

**Symptoms**: Worker logs show connection errors

**Solution**:
```bash
# Check RabbitMQ is running
docker-compose ps rabbitmq

# Verify connection string
echo $CELERY_BROKER_URL

# Restart Celery worker
docker-compose restart celery_worker
```

#### 2. Database Connection Errors

**Symptoms**: Application fails to start with database connection errors

**Solution**:
```bash
# Check database is running
docker-compose ps postgres mongodb

# Verify connection strings
docker-compose exec app env | grep -E '(POSTGRES|MONGODB)'

# Check database logs
docker-compose logs postgres
docker-compose logs mongodb
```

#### 3. Port Already in Use

**Symptoms**: Cannot start containers due to port conflicts

**Solution**:
```bash
# Find process using the port
sudo lsof -i :8000  # or :5432, :27017, etc.

# Kill the process or change port in docker-compose.yml
```

#### 4. ECS Task Failing to Start

**Symptoms**: ECS tasks keep stopping

**Solution**:
```bash
# Check task logs
aws ecs describe-tasks \
    --cluster shorturl-cluster \
    --tasks <task-id>

# View CloudWatch logs
aws logs tail /ecs/shorturl-app --follow

# Check task definition
aws ecs describe-task-definition \
    --task-definition shorturl-task
```

#### 5. CI/CD Pipeline Failures

**Symptoms**: GitHub Actions workflow fails

**Solution**:
1. Check GitHub Actions logs in the Actions tab
2. Verify AWS credentials in repository secrets
3. Ensure ECR repository exists
4. Check ECS cluster and service names match

### Useful Commands

```bash
# Docker
docker-compose ps                    # List running containers
docker-compose logs -f <service>     # Follow logs for a service
docker-compose exec <service> bash   # Access container shell
docker system prune -a               # Clean up Docker resources

# AWS
aws ecs list-tasks --cluster shorturl-cluster
aws ecs describe-services --cluster shorturl-cluster --services shorturl-service
aws ecr describe-images --repository-name shorturl-app
aws logs get-log-events --log-group-name /ecs/shorturl-app --log-stream-name <stream>

# Git
git status
git log --oneline -10
git show <commit-hash>
```

## Environment Variables Reference

See `.env.example` for a complete list of environment variables.

Key variables:
- `POSTGRES_SQL_URL`: PostgreSQL connection string
- `MONGODB_URL`: MongoDB connection string
- `REDIS_URL`: Redis connection string
- `CELERY_BROKER_URL`: RabbitMQ connection for Celery
- `SECRET_KEY`: JWT secret key
- `OPENAI_API_KEY`: OpenAI API key
- `ENVIRONMENT`: `development` or `production`

## Security Best Practices

1. **Never commit sensitive data**
   - Keep `.env` in `.gitignore`
   - Use AWS Secrets Manager for production secrets

2. **Use strong passwords**
   - Generate random passwords for databases
   - Rotate credentials regularly

3. **Enable SSL/TLS**
   - Use ACM certificates with ALB
   - Configure HTTPS in nginx

4. **Network security**
   - Use private subnets for databases
   - Restrict security group rules
   - Enable VPC flow logs

5. **Monitor and audit**
   - Enable CloudWatch alarms
   - Use AWS CloudTrail
   - Review access logs regularly

## Support

For issues or questions:
1. Check this documentation
2. Review application logs
3. Check GitHub Issues
4. Contact the development team
