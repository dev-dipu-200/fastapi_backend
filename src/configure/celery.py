# src/configure/celery.py
import os
from celery import Celery
from celery.schedules import crontab

# Get broker URL from environment variable or use default
CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    "amqp://guest:guest@localhost:5672//"
)
CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    "rpc://"
)

celery_app = Celery(
    "workers",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['src.api.home.tasks']  # Include task modules
)

celery_app.conf.beat_schedule = {
    'delete-expire-urls': {
        'task': 'expire_urls_async',  # Matches task name in src.api.home.tasks
        'schedule': crontab(hour=0, minute=0),  # Run daily at midnight
    },
    'sync-user-data': {
        'task': 'src.api.tasks.sync_user_data',
        'schedule': crontab(minute=0, hour='*/1'),  # Run every hour
    },
    'generate-reports': {
        'task': 'src.api.tasks.generate_reports',
        'schedule': crontab(hour=3, minute=30, day_of_week='mon'),  # Run weekly on Monday at 3:30 AM
    },
    'cleanup-logs': {
        'task': 'src.api.tasks.cleanup_logs',
        'schedule': crontab(hour=1, minute=0, day_of_month='1'),  # Run monthly on the 1st at 1:00 AM
    },
}

# Update Celery configuration
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600, 
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_ignore_result=False,
)