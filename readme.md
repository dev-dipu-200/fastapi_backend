celery -A celery_worker.celery worker --loglevel=info


# Alembic command 

- alembic downgrade -1
- alembic revision --autogenerate -m "Test autogenerate"


steps:
- checkout: self
  fetchDepth: 0