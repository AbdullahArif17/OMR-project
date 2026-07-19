from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import models  # noqa: F401 - registers every mapped table
from config import settings
from database import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def migration_url() -> str:
    if not os.getenv("DATABASE_URL_DIRECT", "").strip():
        raise RuntimeError(
            "DATABASE_URL_DIRECT is required for migrations; use the direct "
            "Neon connection instead of the pooled application URL"
        )
    return settings.database_url_direct


def run_migrations_offline() -> None:
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        {"sqlalchemy.url": migration_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
                render_as_batch=connection.dialect.name == "sqlite",
                transaction_per_migration=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
