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
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

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


@pytest.fixture
async def api_client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """The real app over ASGI, talking to the container.

    `get_session` is overridden so requests use this test's engine rather than the process-wide one
    built from `DATABASE_URL`; nothing else about the app is substituted, so routing, dependencies,
    validation and serialization are all the production code paths.
    """
    from carpool_api.db import get_session
    from carpool_api.main import create_app

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://carpool.test"
    ) as client:
        yield client


@pytest.fixture
async def organizer_event(api_client: AsyncClient) -> tuple[str, dict[str, str]]:
    """An open event, and the headers that administer it.

    For tests whose subject is something *on* an event rather than event creation itself; the event
    endpoints keep their own payload builder, because varying its fields is what they test.
    """
    response = await api_client.post(
        "/v1/events",
        json={
            "name": "Tuesday practice",
            "destination": {
                "address": "500 E Liberty St, Ann Arbor, MI",
                "lat": 42.2808,
                "lng": -83.7430,
            },
            "arrival_at": "2026-09-22T16:00:00-04:00",
            "ends_at": "2026-09-22T18:00:00-04:00",
            "timezone": "America/Detroit",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["event"]["public_id"], {"Authorization": f"Bearer {body['organizer_token']}"}
