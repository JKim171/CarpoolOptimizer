"""A real Postgres, from the same image production runs.

Never SQLite: the schema uses PostGIS types, partial indexes, citext and enums, none of which
SQLite has, so a SQLite test would pass while the real schema was broken (docs/design.md 10).

The container runs `carpool-postgres:16`, built from docker/postgres. If the image is missing the
module skips with an explanatory message rather than failing obscurely.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

IMAGE = "carpool-postgres:16"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _image_present() -> bool:
    result = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, check=False)
    return result.returncode == 0


@pytest.fixture(scope="session")
def alembic_ini() -> Path:
    return ALEMBIC_INI


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    pytest.importorskip("testcontainers", reason="testcontainers is not installed")
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:  # testcontainers < 4.13 kept it at the old path
        from testcontainers.postgres import PostgresContainer

    if not _image_present():
        pytest.skip(f"{IMAGE} not built -- run `make db`")

    with PostgresContainer(IMAGE, driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> Iterator[str]:
    """The container with every migration applied -- the schema as production will have it."""
    from alembic import command
    from alembic.config import Config

    from carpool_api.config import get_settings

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_url
    get_settings.cache_clear()
    try:
        command.upgrade(Config(str(ALEMBIC_INI)), "head")
        yield postgres_url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    try:
        yield engine
    finally:
        await engine.dispose()
