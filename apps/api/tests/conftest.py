import os
from collections.abc import Callable, Iterator

import pytest

# Settings are required, and importing the app reads them. Set a URL before any carpool_api import
# so the suite does not depend on a developer's .env. Nothing here connects: /healthz touches no
# database, and the /readyz tests supply their own session.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

from fastapi.testclient import TestClient

from carpool_api.db import get_session
from carpool_api.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def client_with_session() -> Iterator[Callable[[object], TestClient]]:
    """Build a client whose request session is `stub`, so readiness is tested without Postgres."""
    clients = []

    def build(stub: object) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_session] = lambda: stub
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        return c

    yield build
    for c in clients:
        c.__exit__(None, None, None)
