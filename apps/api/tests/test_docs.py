"""The schema and docs pages: served in development, absent in production.

Nothing calls them in production -- the web client's types are generated at build time -- and a
public Swagger page competes with the landing page in search results for the brand name.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from carpool_api.config import get_settings
from carpool_api.contract import openapi_document
from carpool_api.main import create_app

DOCS_PATHS = ["/docs", "/redoc", "/openapi.json"]


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.mark.parametrize("path", DOCS_PATHS)
def test_development_serves_the_docs(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.usefixtures("production")
@pytest.mark.parametrize("path", DOCS_PATHS)
def test_production_serves_no_docs(path):
    with TestClient(create_app()) as c:
        assert c.get(path).status_code == 404


@pytest.mark.usefixtures("production")
def test_production_still_builds_the_contract():
    """`make openapi` builds the schema from the routes, not from the URL that serves it, so the
    generated contract does not depend on which environment it is built in."""
    assert openapi_document()["paths"]
