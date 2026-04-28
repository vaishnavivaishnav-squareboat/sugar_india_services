import sys
import os
from pathlib import Path

# Ensure sugar_india_services/ is on sys.path so app.* imports resolve
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from logging.config import fileConfig
from sqlalchemy import create_engine, engine_from_config
from sqlalchemy import pool
from alembic import context

# Import Base and all ORM models so alembic can detect them for autogenerate
from app.db.orm import Base  # noqa: F401
from app.db.orm import Lead, OutreachEmail, City, PipelineRun, Segment, Contact  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_database_url():
    """
    Resolve DATABASE_URL and convert asyncpg URL
    to psycopg2 URL for Alembic migrations.

    FastAPI uses:
        postgresql+asyncpg://

    Alembic must use:
        postgresql://
    """

    url = config.get_main_option("sqlalchemy.url")

    if not url or ("${" in url and "}" in url):
        url = os.environ.get("DATABASE_URL")

    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set in environment and alembic.ini does not provide sqlalchemy.url"
        )

    # IMPORTANT FIX:
    # Convert asyncpg URL → sync psycopg2 URL
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace(
            "postgresql+asyncpg://",
            "postgresql://",
            1
        )

    return url


def run_migrations_offline() -> None:
    """
    Run migrations in offline mode.
    """

    url = get_database_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in online mode.
    """

    url = get_database_url()

    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()