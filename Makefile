.PHONY: help build up down restart logs clean test deploy

help:
	@echo "Available commands:"
	@echo "  make build        - Build Docker images"
	@echo "  make up           - Start all services"
	@echo "  make down         - Stop all services"
	@echo "  make restart      - Restart all services"
	@echo "  make logs         - View logs from all services"
	@echo "  make logs-app     - View application logs"
	@echo "  make logs-celery  - View Celery worker logs"
	@echo "  make logs-beat    - View Celery beat logs"
	@echo "  make clean        - Remove containers and volumes"
	@echo "  make shell        - Access application shell"
	@echo "  make test         - Run tests"
	@echo "  make migrate      - Run database migrations"
	@echo "  make deploy-aws   - Deploy to AWS"

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

logs-app:
	docker-compose logs -f app

logs-celery:
	docker-compose logs -f celery_worker

logs-beat:
	docker-compose logs -f celery_beat

logs-nginx:
	docker-compose logs -f nginx

clean:
	docker-compose down -v
	rm -rf logs/*

shell:
	docker-compose exec app bash

test:
	docker-compose exec app pytest

migrate:
	docker-compose exec app alembic upgrade head

celery-status:
	docker-compose exec celery_worker celery -A src.configure.celery:celery_app inspect active

deploy-aws:
	chmod +x aws/scripts/deploy.sh
	./aws/scripts/deploy.sh

setup-aws-infra:
	chmod +x aws/scripts/setup-infrastructure.sh
	./aws/scripts/setup-infrastructure.sh
