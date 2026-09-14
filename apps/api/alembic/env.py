"""Alembic environment.

The database URL comes from the environment (`DATABASE_URL`), never from `alembic.ini` -- that file
is committed and a connection string carries a password.

`target_metadata` is the models' metadata, so the models are the source of truth and autogenerate
diffs against them (docs/design.md 5). `test_schema.py` fails the build if the two drift.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from carpool_api.config import get_settings
from carpool_api.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


#: Tables installed by `create extension postgis` itself. They belong to the extension, not to this
#: schema, so autogenerate must not propose dropping them -- the drift test could never pass.
POSTGIS_OWNED_TABLES = {"spatial_ref_sys", "geography_columns", "geometry_columns"}


def include_object(
    obj: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object,
) -> bool:
    return not (type_ == "table" and name in POSTGIS_OWNED_TABLES)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting -- used to review a migration before it runs."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
