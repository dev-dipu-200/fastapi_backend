# Docker Quick Start Guide

## Getting Started in 3 Steps

### 1. Configure Environment
```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your API keys and configuration
nano .env  # or use your favorite editor
```

### 2. Start the Application
```bash
# Using Make (recommended)
make up

# Or using docker-compose directly
docker-compose up -d
```

### 3. Access the Application
- **API**: http://localhost/api/ or http://localhost:8000/api/
- **RabbitMQ Management**: http://localhost:15672 (login: guest/guest)

## Common Commands

### Using Make
```bash
make help          # Show all available commands
make logs          # View all logs
make logs-app      # View application logs
make logs-celery   # View Celery worker logs
make restart       # Restart all services
make down          # Stop all services
make clean         # Remove all containers and volumes
make shell         # Access application shell
```

### Using Docker Compose
```bash
# View logs
docker-compose logs -f
docker-compose logs -f app
docker-compose logs -f celery_worker

# Restart specific service
docker-compose restart app

# Stop services
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

## Service Overview

Your Docker setup includes:

| Service | Port | Description |
|---------|------|-------------|
| **app** | 8000 | FastAPI application |
| **nginx** | 80, 443 | Reverse proxy |
| **postgres** | 5432 | PostgreSQL database |
| **mongodb** | 27017 | MongoDB database |
| **redis** | 6379 | Redis cache |
| **rabbitmq** | 5672, 15672 | Message broker |
| **celery_worker** | - | Async task worker |
| **celery_beat** | - | Task scheduler |

## Application Logs

Logs are stored in two places:

1. **Docker logs** (via docker-compose logs)
2. **File logs** in `./logs/` directory:
   - `app.log` - General application logs
   - `error.log` - Error logs only
   - `celery.log` - Celery tasks logs
   - `celery_worker.log` - Celery worker logs
   - `celery_beat.log` - Celery beat logs

View file logs:
```bash
tail -f logs/app.log
tail -f logs/error.log
tail -f logs/celery.log
```

## Celery Tasks

### View Running Tasks
```bash
make celery-status

# Or directly
docker-compose exec celery_worker celery -A src.configure.celery:celery_app inspect active
```

### View Registered Tasks
```bash
docker-compose exec celery_worker celery -A src.configure.celery:celery_app inspect registered
```

### View Scheduled Tasks
```bash
docker-compose exec celery_worker celery -A src.configure.celery:celery_app inspect scheduled
```

## Database Operations

### Run Migrations
```bash
make migrate

# Or directly
docker-compose exec app alembic upgrade head
```

### Access PostgreSQL
```bash
docker-compose exec postgres psql -U dipu -d fastapi_db
```

### Access MongoDB
```bash
docker-compose exec mongodb mongosh
```

### Access Redis
```bash
docker-compose exec redis redis-cli
```

## Development Workflow

### 1. Make Code Changes
Edit your files locally - changes will be reflected in the container via volume mounts.

### 2. Restart Application (if needed)
```bash
make restart
# Or just restart the app service
docker-compose restart app
```

### 3. View Logs
```bash
make logs-app
```

### 4. Run Tests
```bash
make test
```

## Troubleshooting

### Port Already in Use
If you get a port conflict:
```bash
# Find what's using the port
sudo lsof -i :8000  # or :5432, :27017, etc.

# Stop the process or change the port in docker-compose.yml
```

### Container Won't Start
```bash
# View detailed logs
docker-compose logs <service-name>

# Check container status
docker-compose ps

# Restart the service
docker-compose restart <service-name>
```

### Database Connection Issues
```bash
# Check if databases are running
docker-compose ps postgres mongodb

# View database logs
docker-compose logs postgres
docker-compose logs mongodb

# Verify environment variables
docker-compose exec app env | grep -E '(POSTGRES|MONGODB)'
```

### Celery Worker Issues
```bash
# Check RabbitMQ status
docker-compose ps rabbitmq
docker-compose logs rabbitmq

# Restart Celery
docker-compose restart celery_worker celery_beat

# Check broker connection
docker-compose exec app env | grep CELERY
```

### Complete Reset
If things are really broken:
```bash
# Stop everything and remove volumes
make clean

# Rebuild and start fresh
make build
make up
```

## Performance Tuning

### Limit Resource Usage
Edit `docker-compose.yml` to add resource limits:
```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          memory: 512M
```

### Scale Services
```bash
# Run multiple Celery workers
docker-compose up -d --scale celery_worker=3
```

## Next Steps

- Read [DEPLOYMENT.md](DEPLOYMENT.md) for AWS deployment
- Configure your API keys in `.env`
- Set up SSL certificates for production
- Enable monitoring and alerting

## Need Help?

- Check logs: `make logs`
- View this guide: `cat DOCKER_QUICKSTART.md`
- Read full deployment guide: `cat DEPLOYMENT.md`
- Check container status: `docker-compose ps`
