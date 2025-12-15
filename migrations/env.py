import os
import sys
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context

# Add project root to sys.path to ensure imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import your settings and models
from src.configure.settings import settings
from src.models.user_model import User
from src.models.url_model import SortUrls
from src.models.click_model import Clicks
from src.configure.database import Base

# Alembic Config object
config = context.config

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData for autogenerate support
target_metadata = Base.metadata

# Override the database URL to use synchronous psycopg2 driver
sync_db_url = settings.POSTGRES_SQL_URL.replace("+asyncpg", "+psycopg2")
config.set_main_option("sqlalchemy.url", sync_db_url)

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode."""
    # Create a synchronous engine
    connectable = create_engine(sync_db_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()