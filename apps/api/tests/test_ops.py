"""The liveness/readiness split is a deployment contract, so it is asserted rather than assumed."""

import pytest
from sqlalchemy.exc import OperationalError

from carpool_api.db import get_session


class WorkingSession:
    async def execute(self, statement):
        return None


class BrokenSession:
    async def execute(self, statement):
        raise OperationalError("select 1", {}, Exception("connection refused"))


def test_healthz_is_ok(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_does_not_touch_the_database(client):
    """A database outage must not make the process look dead -- restarting it would not help."""

    def explode():
        raise AssertionError("/healthz must not open a database session")

    client.app.dependency_overrides[get_session] = explode

    assert client.get("/healthz").status_code == 200


def test_readyz_reports_ready_when_the_database_answers(client_with_session):
    response = client_with_session(WorkingSession()).get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "up"}


def test_readyz_is_503_when_the_database_is_down(client_with_session):
    response = client_with_session(BrokenSession()).get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "down"}


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_ops_endpoints_are_unversioned(client, path):
    """Alarms and load balancers should not have to track an API version."""
    assert client.get(f"/v1{path}").status_code == 404
