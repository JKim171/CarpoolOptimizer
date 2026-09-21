"""The event endpoints against a real Postgres (docs/design.md 6).

Against the real database rather than a mocked session, because most of what these endpoints
promise -- the coordinate round trip through PostGIS, the unique handle, the server-side defaults --
is the database's behaviour, and a stubbed session would assert only that the handler calls methods.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ARRIVAL = datetime(2026, 9, 22, 16, 0, tzinfo=UTC)

# Somewhere in Ann Arbor. Latitude positive, longitude negative -- see test_security.py.
LAT = 42.2808
LNG = -83.7430


def payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Tuesday practice",
        "destination": {
            "address": "500 E Liberty St, Ann Arbor, MI",
            "lat": LAT,
            "lng": LNG,
        },
        "arrival_at": ARRIVAL.isoformat(),
        "ends_at": (ARRIVAL + timedelta(hours=2)).isoformat(),
        "timezone": "America/Detroit",
    }
    body.update(overrides)
    return body


async def create_event(client: AsyncClient, **overrides: Any) -> tuple[dict[str, Any], str]:
    """An event and the headers that administer it."""
    response = await client.post("/v1/events", json=payload(**overrides))
    assert response.status_code == 201, response.text
    body = response.json()
    return body, body["organizer_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_returns_the_event_and_a_token_once(api_client: AsyncClient) -> None:
    body, token = await create_event(api_client)
    event = body["event"]

    assert event["name"] == "Tuesday practice"
    assert event["status"] == "open"
    assert event["participants_version"] == 0
    assert event["public_id"]
    assert token
    assert datetime.fromisoformat(body["organizer_token_expires_at"]) > datetime.now(UTC)


async def test_create_advertises_the_event_location(api_client: AsyncClient) -> None:
    response = await api_client.post("/v1/events", json=payload())

    public_id = response.json()["event"]["public_id"]
    assert response.headers["Location"] == f"/v1/events/{public_id}"


async def test_coordinates_survive_the_round_trip_unswapped(api_client: AsyncClient) -> None:
    """The lat/lng pin at the storage boundary.

    A swap raises nothing and relocates the destination by ~9,000 km, so it has to be asserted
    somewhere the value has actually been through PostGIS.
    """
    body, token = await create_event(api_client)
    public_id = body["event"]["public_id"]

    fetched = await api_client.get(f"/v1/events/{public_id}", headers=auth(token))

    destination = fetched.json()["destination"]
    assert destination["lat"] == LAT
    assert destination["lng"] == LNG
    assert destination["address"] == "500 E Liberty St, Ann Arbor, MI"


async def test_only_the_token_digest_is_stored(
    api_client: AsyncClient, engine: AsyncEngine
) -> None:
    """A database dump must not hand over event control (docs/design.md 6.1)."""
    body, token = await create_event(api_client)

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "select t.kind, t.token_hash from event_tokens t"
                    " join events e on e.id = t.event_id where e.public_id = :p"
                ),
                {"p": body["event"]["public_id"]},
            )
        ).all()

    assert [row.kind for row in rows] == ["organizer"]
    assert rows[0].token_hash == hashlib.sha256(token.encode()).digest()
    assert token.encode() not in rows[0].token_hash


async def test_get_requires_a_token(api_client: AsyncClient) -> None:
    body, _ = await create_event(api_client)

    response = await api_client.get(f"/v1/events/{body['event']['public_id']}")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_a_wrong_token_is_rejected(api_client: AsyncClient) -> None:
    body, _ = await create_event(api_client)

    response = await api_client.get(
        f"/v1/events/{body['event']['public_id']}", headers=auth("not-the-token")
    )

    assert response.status_code == 401


async def test_one_events_token_does_not_open_another(api_client: AsyncClient) -> None:
    """Tokens are scoped to their event, and the join is what enforces it."""
    mine, my_token = await create_event(api_client)
    theirs, _ = await create_event(api_client, name="Someone else's event")

    response = await api_client.get(
        f"/v1/events/{theirs['event']['public_id']}", headers=auth(my_token)
    )

    assert response.status_code == 401
    assert mine["event"]["public_id"] != theirs["event"]["public_id"]


async def test_an_unknown_event_is_401_not_404(api_client: AsyncClient) -> None:
    """Deliberate: a 404 here would report which handles exist to an unauthenticated caller."""
    _, token = await create_event(api_client)

    response = await api_client.get("/v1/events/zzzzzzzzzz", headers=auth(token))

    assert response.status_code == 401


async def test_an_expired_token_is_rejected(api_client: AsyncClient, engine: AsyncEngine) -> None:
    body, token = await create_event(api_client)
    public_id = body["event"]["public_id"]

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "update event_tokens set expires_at = now() - interval '1 second'"
                " where event_id = (select id from events where public_id = :p)"
            ),
            {"p": public_id},
        )

    assert (await api_client.get(f"/v1/events/{public_id}", headers=auth(token))).status_code == 401


async def test_a_revoked_token_is_rejected(api_client: AsyncClient, engine: AsyncEngine) -> None:
    body, token = await create_event(api_client)
    public_id = body["event"]["public_id"]

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "update event_tokens set revoked_at = now()"
                " where event_id = (select id from events where public_id = :p)"
            ),
            {"p": public_id},
        )

    assert (await api_client.get(f"/v1/events/{public_id}", headers=auth(token))).status_code == 401


async def test_an_event_must_end_after_it_starts(api_client: AsyncClient) -> None:
    """Rejected at the edge, so the caller gets a named field rather than a constraint violation."""
    response = await api_client.post(
        "/v1/events", json=payload(ends_at=(ARRIVAL - timedelta(hours=1)).isoformat())
    )

    assert response.status_code == 422
    assert "ends_at must be after arrival_at" in response.text


async def test_a_naive_timestamp_is_rejected(api_client: AsyncClient) -> None:
    """Without an offset there is no instant, only a guess about whose clock was meant."""
    response = await api_client.post("/v1/events", json=payload(arrival_at="2026-09-22T16:00:00"))

    assert response.status_code == 422


async def test_an_unknown_timezone_is_rejected(api_client: AsyncClient) -> None:
    response = await api_client.post("/v1/events", json=payload(timezone="Mars/Olympus_Mons"))

    assert response.status_code == 422
    assert "unknown IANA time zone" in response.text


async def test_an_unexpected_field_is_rejected(api_client: AsyncClient) -> None:
    """A mistyped field must not be silently dropped -- the event would look saved and correct."""
    response = await api_client.post("/v1/events", json=payload(end_at="oops"))

    assert response.status_code == 422


async def test_coordinates_must_be_on_earth(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/v1/events",
        json=payload(destination={"address": "1 Main St", "lat": 91.0, "lng": 0.0}),
    )

    assert response.status_code == 422


async def test_patch_updates_named_fields_only(api_client: AsyncClient) -> None:
    body, token = await create_event(api_client)
    public_id = body["event"]["public_id"]

    response = await api_client.patch(
        f"/v1/events/{public_id}", headers=auth(token), json={"name": "Thursday practice"}
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Thursday practice"
    assert updated["destination"] == body["event"]["destination"]
    assert updated["arrival_at"] == body["event"]["arrival_at"]


async def test_patch_moves_the_destination_as_a_unit(api_client: AsyncClient) -> None:
    body, token = await create_event(api_client)

    response = await api_client.patch(
        f"/v1/events/{body['event']['public_id']}",
        headers=auth(token),
        json={
            "destination": {
                "address": "1000 S State St, Ann Arbor, MI",
                "lat": 42.27,
                "lng": -83.74,
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["destination"] == {
        "address": "1000 S State St, Ann Arbor, MI",
        "lat": 42.27,
        "lng": -83.74,
    }


async def test_patch_rejects_an_address_without_coordinates(api_client: AsyncClient) -> None:
    """There is no geocoder yet, so an address alone would disagree with the stored point."""
    body, token = await create_event(api_client)

    response = await api_client.patch(
        f"/v1/events/{body['event']['public_id']}",
        headers=auth(token),
        json={"destination": {"address": "1000 S State St, Ann Arbor, MI"}},
    )

    assert response.status_code == 422


async def test_patch_cannot_invert_the_event_window(api_client: AsyncClient) -> None:
    """One field, valid on its own, that makes the pair invalid."""
    body, token = await create_event(api_client)

    response = await api_client.patch(
        f"/v1/events/{body['event']['public_id']}",
        headers=auth(token),
        json={"arrival_at": (ARRIVAL + timedelta(hours=5)).isoformat()},
    )

    assert response.status_code == 422
    assert "ends_at must be after arrival_at" in response.text


async def test_patch_requires_a_token(api_client: AsyncClient) -> None:
    body, _ = await create_event(api_client)

    response = await api_client.patch(
        f"/v1/events/{body['event']['public_id']}", json={"name": "Hijacked"}
    )

    assert response.status_code == 401


async def test_lock_freezes_the_event_and_is_idempotent(api_client: AsyncClient) -> None:
    """A double-tapped button is not a conflict."""
    body, token = await create_event(api_client)
    url = f"/v1/events/{body['event']['public_id']}/lock"

    first = await api_client.post(url, headers=auth(token))
    second = await api_client.post(url, headers=auth(token))

    assert first.status_code == 200
    assert first.json()["status"] == "locked"
    assert second.status_code == 200
    assert second.json()["status"] == "locked"


async def test_a_locked_event_can_still_be_corrected(api_client: AsyncClient) -> None:
    """Locking freezes the roster, not the venue -- see `patch_event`."""
    body, token = await create_event(api_client)
    public_id = body["event"]["public_id"]
    await api_client.post(f"/v1/events/{public_id}/lock", headers=auth(token))

    response = await api_client.patch(
        f"/v1/events/{public_id}", headers=auth(token), json={"name": "Moved indoors"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "locked"


async def test_an_archived_event_is_immutable(api_client: AsyncClient, engine: AsyncEngine) -> None:
    body, token = await create_event(api_client)
    public_id = body["event"]["public_id"]

    async with engine.begin() as conn:
        await conn.execute(
            text("update events set status = 'archived' where public_id = :p"), {"p": public_id}
        )

    patched = await api_client.patch(
        f"/v1/events/{public_id}", headers=auth(token), json={"name": "Nope"}
    )
    locked = await api_client.post(f"/v1/events/{public_id}/lock", headers=auth(token))

    assert patched.status_code == 409
    assert locked.status_code == 409


async def test_ops_endpoints_are_reachable_alongside_the_event_router(
    api_client: AsyncClient,
) -> None:
    """Mounting /v1/events must not shadow the unversioned ops paths."""
    assert (await api_client.get("/healthz")).status_code == 200
    assert (await api_client.get("/readyz")).json() == {"status": "ready", "database": "up"}


async def test_event_creation_is_rate_limited_per_client(api_client: AsyncClient) -> None:
    """Each event mints a token good for a roster and solves, so creation bounds disk use."""
    from carpool_api.ratelimit import CREATE_EVENT

    for _ in range(CREATE_EVENT.limit):
        await create_event(api_client)

    response = await api_client.post("/v1/events", json=payload())

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert response.json()["detail"].startswith("Too many events created from this network")
