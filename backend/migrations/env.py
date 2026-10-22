"""Окружение миграций.

Адрес базы и метаданные берутся из приложения, поэтому миграции всегда смотрят
на ту же базу, с которой работает API.
"""

from logging.config import fileConfig

from alembic import context

from app.core.db import Base, engine
from app.core.settings import settings

# Импорт моделей нужен, чтобы метаданные знали обо всех таблицах.
from app import models  # noqa: F401
from app.staff_pipeline import models as staff_pipeline_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # На SQLite изменение таблиц возможно только пересозданием.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
