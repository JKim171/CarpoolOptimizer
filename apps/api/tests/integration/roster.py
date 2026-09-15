"""Roster-building helpers shared by the optimization and solution suites.

Not a `test_` module and not `conftest.py`: these are plain functions that several suites call, and
pytest puts each test file's own directory on `sys.path`, so a flat `from roster import ...`
resolves. A module rather than fixtures because they take arguments and return values -- a fixture
wrapping a callable would be indirection for its own sake.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

Event = tuple[str, dict[str, str]]

# Four points around Ann Arbor, spread out enough that pickups differ and every detour is non-zero.
# Deliberately none of them at the venue (42.2808, -83.7430, from the `organizer_event` fixture): a
# passenger living exactly at the destination costs zero detour and zero ride time, which quietly
# makes any test about either of those pass for the wrong reason.
HOMES = {
    "driver": (42.2936, -83.7101),
    "east": (42.2790, -83.7350),
    "west": (42.2681, -83.7514),
    "north": (42.3100, -83.7200),
}


def person(name: str, key: str, **overrides: Any) -> dict[str, Any]:
    lat, lng = HOMES[key]
    body: dict[str, Any] = {
        "display_name": name,
        "pickup": {"address": f"{name} house, Ann Arbor, MI", "lat": lat, "lng": lng},
        "role": "passenger",
    }
    body.update(overrides)
    return body


async def add(client: AsyncClient, event: Event, body: dict[str, Any]) -> dict[str, Any]:
    public_id, headers = event
    response = await client.post(f"/v1/events/{public_id}/participants", headers=headers, json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()["participant"]
    return result


async def seed_roster(client: AsyncClient, event: Event) -> dict[str, dict[str, Any]]:
    """One driver with three seats and three passengers: everybody fits, nobody is unassigned."""
    return {
        "driver": await add(
            client, event, person("Sam", "driver", role="driver", seats_available=3)
        ),
        "east": await add(client, event, person("Ada", "east")),
        "west": await add(client, event, person("Bo", "west")),
        "north": await add(client, event, person("Cy", "north")),
    }


async def optimize(
    client: AsyncClient, event: Event, *, expect: int = 202, **kwargs: Any
) -> dict[str, Any]:
    public_id, headers = event
    response = await client.post(f"/v1/events/{public_id}/optimizations", headers=headers, **kwargs)
    assert response.status_code == expect, response.text
    result: dict[str, Any] = response.json()
    return result


async def other_event(client: AsyncClient) -> Event:
    """A second event with its own organizer token, for cross-event isolation checks."""
    response = await client.post(
        "/v1/events",
        json={
            "name": "Another event",
            "destination": {"address": "1 Main St", "lat": 42.0, "lng": -83.0},
            "arrival_at": "2026-10-01T16:00:00-04:00",
            "ends_at": "2026-10-01T18:00:00-04:00",
            "timezone": "America/Detroit",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["event"]["public_id"], {"Authorization": f"Bearer {body['organizer_token']}"}
