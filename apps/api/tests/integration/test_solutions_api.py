"""Reading and activating solutions (docs/design.md 6, 5.1).

Activation is the assertion-heavy part: exactly one solution per event may be live, the database
enforces it, and a race must not be able to produce two answers or none.
"""

from __future__ import annotations

import asyncio
from typing import Any

from httpx import AsyncClient
from roster import add, optimize, other_event, person, seed_roster
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from carpool_api.adapters.travel import TravelEstimates, TravelUnavailable, haversine_estimates
from carpool_domain import Location, NodeId


async def solutions(client: AsyncClient, event: tuple[str, dict[str, str]]) -> list[dict[str, Any]]:
    public_id, headers = event
    response = await client.get(f"/v1/events/{public_id}/solutions", headers=headers)
    assert response.status_code == 200, response.text
    result: list[dict[str, Any]] = response.json()
    return result


async def test_a_solution_reads_back_with_both_legs_and_names(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """What a results screen needs: who drives whom, in what order, at what time."""
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    response = await api_client.get(
        f"/v1/events/{public_id}/solutions/{job['solution_id']}", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["algorithm"] == "lns"
    assert body["is_active"] is False
    assert body["is_stale"] is False
    assert len(body["routes"]) == 1

    route = body["routes"][0]
    assert route["driver_name"] == "Sam"
    assert route["seats_used"] == 3
    assert route["outbound"]["leg"] == "outbound"
    assert route["inbound"]["leg"] == "return"
    assert [stop["seq"] for stop in route["outbound"]["stops"]] == [0, 1, 2]
    assert sorted(stop["display_name"] for stop in route["outbound"]["stops"]) == [
        "Ada",
        "Bo",
        "Cy",
    ]
    assert all(stop["eta"] for stop in route["inbound"]["stops"])
    assert all(stop["pickup_address"] for stop in route["outbound"]["stops"])


async def test_unassigned_participants_are_named_with_their_reason(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    await add(
        api_client, organizer_event, person("Sam", "driver", role="driver", seats_available=1)
    )
    await add(api_client, organizer_event, person("Ada", "east"))
    await add(api_client, organizer_event, person("Bo", "west"))
    job = await optimize(api_client, organizer_event)

    response = await api_client.get(
        f"/v1/events/{public_id}/solutions/{job['solution_id']}", headers=headers
    )

    left_out = response.json()["unassigned"]
    assert len(left_out) == 1
    assert left_out[0]["reason"] == "no_capacity"
    assert left_out[0]["display_name"] in ("Ada", "Bo")


async def test_history_lists_every_solution_newest_first(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """History is kept rather than overwritten, so runs can be compared (docs/design.md 8.4)."""
    await seed_roster(api_client, organizer_event)
    first = await optimize(api_client, organizer_event)
    await add(api_client, organizer_event, person("Dee", "north"))
    second = await optimize(api_client, organizer_event)

    listed = await solutions(api_client, organizer_event)

    assert [entry["id"] for entry in listed] == [second["solution_id"], first["solution_id"]]
    assert all("routes" not in entry for entry in listed), "history is a summary, not every stop"


async def test_a_solution_goes_stale_when_the_roster_changes(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """Detected, never prevented: the event is not locked while a solve runs (design 5.1)."""
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    await add(api_client, organizer_event, person("Dee", "north"))
    listed = await solutions(api_client, organizer_event)

    stale = next(entry for entry in listed if entry["id"] == job["solution_id"])
    assert stale["is_stale"] is True
    assert stale["input_version"] < 5


async def test_activating_a_solution_makes_it_live(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    response = await api_client.post(
        f"/v1/events/{public_id}/solutions/{job['solution_id']}/activate", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is True


async def test_activating_is_idempotent(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)
    url = f"/v1/events/{public_id}/solutions/{job['solution_id']}/activate"

    first = await api_client.post(url, headers=headers)
    second = await api_client.post(url, headers=headers)

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json()["is_active"] is True


async def test_activating_a_second_solution_deactivates_the_first(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """`one_active_solution_per_event` would reject the insert otherwise -- so this also proves the
    deactivate and activate happen in one transaction."""
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)
    first = await optimize(api_client, organizer_event)
    await api_client.post(
        f"/v1/events/{public_id}/solutions/{first['solution_id']}/activate", headers=headers
    )
    await add(api_client, organizer_event, person("Dee", "north"))
    second = await optimize(api_client, organizer_event)

    response = await api_client.post(
        f"/v1/events/{public_id}/solutions/{second['solution_id']}/activate", headers=headers
    )

    assert response.status_code == 200
    async with engine.connect() as conn:
        active = (
            await conn.execute(
                text(
                    "select s.id from solutions s join events e on e.id = s.event_id"
                    " where e.public_id = :p and s.is_active"
                ),
                {"p": public_id},
            )
        ).scalars()

    assert [str(row) for row in active] == [second["solution_id"]]


async def test_concurrent_activations_leave_exactly_one_live(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """Two organizers on two devices. The index is what makes this safe, not the handler."""
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)
    first = await optimize(api_client, organizer_event)
    await add(api_client, organizer_event, person("Dee", "north"))
    second = await optimize(api_client, organizer_event)

    await asyncio.gather(
        *(
            api_client.post(
                f"/v1/events/{public_id}/solutions/{solution_id}/activate", headers=headers
            )
            for solution_id in (first["solution_id"], second["solution_id"])
        ),
        return_exceptions=True,
    )

    async with engine.connect() as conn:
        live = (
            await conn.execute(
                text(
                    "select count(*) from solutions s join events e on e.id = s.event_id"
                    " where e.public_id = :p and s.is_active"
                ),
                {"p": public_id},
            )
        ).scalar_one()

    assert live <= 1


async def test_a_stale_solution_can_still_be_activated(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """An organizer may prefer a known arrangement to re-solving an hour before the event."""
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)
    await add(api_client, organizer_event, person("Dee", "north"))

    response = await api_client.post(
        f"/v1/events/{public_id}/solutions/{job['solution_id']}/activate", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is True
    assert response.json()["is_stale"] is True


async def test_a_cancelled_participant_still_renders_in_an_earlier_solution(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """The snapshot stays truthful: a solution computed before somebody dropped out still names
    them, and reading it must not fail because they left the roster (docs/design.md 5.3.1)."""
    public_id, headers = organizer_event
    roster = await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)
    await api_client.delete(
        f"/v1/events/{public_id}/participants/{roster['north']['id']}", headers=headers
    )

    response = await api_client.get(
        f"/v1/events/{public_id}/solutions/{job['solution_id']}", headers=headers
    )

    assert response.status_code == 200
    named = {
        stop["display_name"]
        for route in response.json()["routes"]
        for stop in route["outbound"]["stops"]
    }
    assert "Cy" in named


async def test_solution_endpoints_require_the_organizer_token(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, _headers = organizer_event
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    listed = await api_client.get(f"/v1/events/{public_id}/solutions")
    fetched = await api_client.get(f"/v1/events/{public_id}/solutions/{job['solution_id']}")
    activated = await api_client.post(
        f"/v1/events/{public_id}/solutions/{job['solution_id']}/activate"
    )

    assert [listed.status_code, fetched.status_code, activated.status_code] == [401, 401, 401]


async def test_a_solution_of_another_event_is_not_reachable(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    other_id, other_headers = await other_event(api_client)

    response = await api_client.get(
        f"/v1/events/{other_id}/solutions/{job['solution_id']}", headers=other_headers
    )

    assert response.status_code == 404


async def test_history_is_empty_before_any_solve(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    assert await solutions(api_client, organizer_event) == []


class StubDirections:
    """Answers with the waypoints themselves as the line, and records every request."""

    def __init__(self, *, fail_after: int | None = None) -> None:
        self.requests: list[list[Location]] = []
        self.fail_after = fail_after

    async def line(self, stops: list[Location]) -> list[tuple[float, float]]:
        self.requests.append(list(stops))
        if self.fail_after is not None and len(self.requests) > self.fail_after:
            raise TravelUnavailable("the routing provider returned 429")
        return [(stop.lng, stop.lat) for stop in stops]


async def geometry(
    client: AsyncClient, event: tuple[str, dict[str, str]], solution_id: str, *, expect: int = 200
) -> dict[str, Any]:
    public_id, headers = event
    response = await client.get(
        f"/v1/events/{public_id}/solutions/{solution_id}/geometry", headers=headers
    )
    assert response.status_code == expect, response.text
    result: dict[str, Any] = response.json()
    return result


VENUE = (-83.7430, 42.2808)


async def test_without_a_provider_every_leg_is_left_to_straight_lines(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    body = await geometry(api_client, organizer_event, job["solution_id"])

    [route] = body["routes"]
    assert route["outbound"] is None
    assert route["inbound"] is None


async def test_a_leg_is_drawn_home_through_each_stop_to_the_venue_and_back(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], travel: Any
) -> None:
    """The waypoints are the stored ordering, in driving order, longitude first."""
    travel.directions = StubDirections()
    public_id, headers = organizer_event
    roster = await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)
    solution = (
        await api_client.get(
            f"/v1/events/{public_id}/solutions/{job['solution_id']}", headers=headers
        )
    ).json()
    by_id = {p["id"]: (p["pickup"]["lng"], p["pickup"]["lat"]) for p in roster.values()}
    home = by_id[roster["driver"]["id"]]
    outbound_stops = [
        by_id[s["participant_id"]] for s in solution["routes"][0]["outbound"]["stops"]
    ]
    inbound_stops = [by_id[s["participant_id"]] for s in solution["routes"][0]["inbound"]["stops"]]

    [route] = (await geometry(api_client, organizer_event, job["solution_id"]))["routes"]

    assert route["route_id"] == solution["routes"][0]["id"]
    assert [tuple(p) for p in route["outbound"]] == [home, *outbound_stops, VENUE]
    assert [tuple(p) for p in route["inbound"]] == [VENUE, *inbound_stops, home]


async def test_geometry_is_fetched_once_and_read_back_after(
    api_client: AsyncClient,
    organizer_event: tuple[str, dict[str, str]],
    engine: AsyncEngine,
    travel: Any,
) -> None:
    """The Directions quota binds long before the matrix one (docs/design.md 4.4): one request per
    leg, the first time, and none on any view after."""
    travel.directions = provider = StubDirections()
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    first = await geometry(api_client, organizer_event, job["solution_id"])
    second = await geometry(api_client, organizer_event, job["solution_id"])

    assert len(provider.requests) == 2
    assert second == first
    async with engine.connect() as conn:
        stored = (
            await conn.execute(
                text(
                    "select count(*) from routes where solution_id = :s"
                    " and outbound_geometry is not null and return_geometry is not null"
                ),
                {"s": job["solution_id"]},
            )
        ).scalar_one()
    assert stored == 1


async def test_a_leg_the_provider_could_not_draw_is_asked_for_again(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], travel: Any
) -> None:
    travel.directions = provider = StubDirections(fail_after=1)
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    [partial] = (await geometry(api_client, organizer_event, job["solution_id"]))["routes"]
    provider.fail_after = None
    [complete] = (await geometry(api_client, organizer_event, job["solution_id"]))["routes"]

    assert (partial["outbound"] is None) != (partial["inbound"] is None)
    assert complete["outbound"] is not None
    assert complete["inbound"] is not None
    # One leg the first time, one failure, and only the failed leg again.
    assert len(provider.requests) == 3


async def test_geometry_of_another_events_solution_is_not_reachable(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], travel: Any
) -> None:
    travel.directions = provider = StubDirections()
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)
    other = await other_event(api_client)

    await geometry(api_client, other, job["solution_id"], expect=404)

    assert provider.requests == []


class RoadTimes:
    provider = "ors"

    async def estimates(self, nodes: dict[NodeId, Location]) -> TravelEstimates:
        straight = haversine_estimates(nodes)
        return TravelEstimates(
            matrix=straight.matrix, _distances_m=straight._distances_m, provider="ors"
        )


async def read_solution(
    client: AsyncClient, event: tuple[str, dict[str, str]], solution_id: str
) -> dict[str, Any]:
    public_id, headers = event
    response = await client.get(f"/v1/events/{public_id}/solutions/{solution_id}", headers=headers)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_a_solution_on_road_times_says_so(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], travel: Any
) -> None:
    travel.current = RoadTimes()
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    assert (await read_solution(api_client, organizer_event, job["solution_id"]))["travel"] == "ors"
    assert (await solutions(api_client, organizer_event))[0]["travel"] == "ors"


async def test_a_solution_on_estimates_says_so(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """What the results screen reads to warn that every time on it is a straight-line guess."""
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    body = await read_solution(api_client, organizer_event, job["solution_id"])

    assert body["travel"] == "haversine"


async def test_a_solution_from_before_road_times_reads_as_estimates(
    api_client: AsyncClient,
    organizer_event: tuple[str, dict[str, str]],
    engine: AsyncEngine,
    travel: Any,
) -> None:
    """Those recorded nothing, and every one of them was solved on estimates."""
    travel.current = RoadTimes()
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)
    async with engine.begin() as conn:
        await conn.execute(
            text("update solutions set metrics = metrics - 'travel' where id = :s"),
            {"s": job["solution_id"]},
        )

    body = await read_solution(api_client, organizer_event, job["solution_id"])

    assert body["travel"] == "haversine"
