"""Optimizing an event end to end (docs/design.md 6, 4.2, 5.1).

These are the tests that prove the roadmap's Week 2 done-condition: create event, add roster,
optimize, fetch routes -- with both legs present. They run against a real Postgres because the whole
point is what gets *written*: a solution, its routes, per-leg stop orderings with ETAs, and a reason
for anyone left out.
"""

from __future__ import annotations

import asyncio

from httpx import AsyncClient
from roster import add, optimize, other_event, person, seed_roster
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_optimizing_an_event_succeeds_inline(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """202 per the async contract, but the answer is already there: Week 2 solves inline."""
    await seed_roster(api_client, organizer_event)

    job = await optimize(api_client, organizer_event)

    assert job["status"] == "succeeded"
    assert job["algorithm"] == "greedy"
    assert job["solution_id"] is not None
    assert job["error"] is None
    assert job["input_version"] == 4
    assert job["finished_at"] is not None


async def test_a_solution_carries_routes_and_both_legs(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """The roadmap's Week 2 done-condition: both legs returned, each with its own ordering."""
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    async with engine.connect() as conn:
        routes = (
            await conn.execute(
                text(
                    "select id, seats_used, total_duration_s, total_distance_m, detour_seconds"
                    " from routes where solution_id = :s"
                ),
                {"s": job["solution_id"]},
            )
        ).all()
        stops = (
            await conn.execute(
                text(
                    "select leg, seq, participant_id, eta from route_stops"
                    " where route_id = :r order by leg, seq"
                ),
                {"r": routes[0].id},
            )
        ).all()

    assert len(routes) == 1
    assert routes[0].seats_used == 3
    assert routes[0].total_duration_s > 0
    assert routes[0].total_distance_m > 0
    assert routes[0].detour_seconds >= 0

    outbound = [s for s in stops if s.leg == "outbound"]
    inbound = [s for s in stops if s.leg == "return"]
    assert len(outbound) == 3
    assert len(inbound) == 3
    assert [s.seq for s in outbound] == [0, 1, 2]
    assert [s.seq for s in inbound] == [0, 1, 2]
    assert all(s.eta is not None for s in stops)


async def test_outbound_pickups_run_in_time_order_and_land_before_arrival(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """ETAs are derived from the ordering, so the two must agree (docs/design.md 8.2)."""
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "select s.seq, s.eta, e.arrival_at from route_stops s"
                    " join routes r on r.id = s.route_id"
                    " join solutions so on so.id = r.solution_id"
                    " join events e on e.id = so.event_id"
                    " where so.id = :s and s.leg = 'outbound' order by s.seq"
                ),
                {"s": job["solution_id"]},
            )
        ).all()

    etas = [row.eta for row in rows]
    assert etas == sorted(etas)
    assert all(row.eta <= row.arrival_at for row in rows)


async def test_return_dropoffs_start_after_the_event_ends(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """The return leg schedules forward from `ends_at`, not backward from anything."""
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "select s.eta, e.ends_at from route_stops s"
                    " join routes r on r.id = s.route_id"
                    " join solutions so on so.id = r.solution_id"
                    " join events e on e.id = so.event_id"
                    " where so.id = :s and s.leg = 'return' order by s.seq"
                ),
                {"s": job["solution_id"]},
            )
        ).all()

    assert rows
    assert all(row.eta >= row.ends_at for row in rows)


async def test_metrics_are_recorded_without_claiming_optimality(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """`gap_to_bound` must be null: greedy has no bound, and zero would read as proven optimal."""
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("select objective_value, metrics, is_active from solutions where id = :s"),
                {"s": job["solution_id"]},
            )
        ).one()

    assert row.objective_value > 0
    assert row.metrics["vehicles"] == 1
    assert row.metrics["drive_s"] > 0
    assert row.metrics["unassigned"] == 0
    assert row.metrics["gap_to_bound"] is None
    assert row.is_active is False, "a fresh solution is not activated automatically"


async def test_an_unassignable_participant_gets_a_reason(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """One seat, two passengers: the second is unassigned because the car is full."""
    await add(
        api_client, organizer_event, person("Sam", "driver", role="driver", seats_available=1)
    )
    await add(api_client, organizer_event, person("Ada", "east"))
    await add(api_client, organizer_event, person("Bo", "west"))

    job = await optimize(api_client, organizer_event)

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("select reason from unassigned_participants where solution_id = :s"),
                {"s": job["solution_id"]},
            )
        ).all()

    assert [row.reason for row in rows] == ["no_capacity"]


async def test_a_roster_with_no_drivers_reports_no_drivers(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """A legitimate answer, not an error: the organizer needs to be told to find a driver."""
    await add(api_client, organizer_event, person("Ada", "east"))
    await add(api_client, organizer_event, person("Bo", "west"))

    job = await optimize(api_client, organizer_event)

    assert job["status"] == "succeeded"
    async with engine.connect() as conn:
        reasons = (
            await conn.execute(
                text("select reason from unassigned_participants where solution_id = :s"),
                {"s": job["solution_id"]},
            )
        ).scalars()

    assert set(reasons) == {"no_drivers"}


async def test_a_detour_cap_is_reported_as_detour_exceeded(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """Minutes in the API, seconds in the solver: the conversion's end-to-end check.

    `west` is off the direct line from the driver to the venue, so collecting them genuinely costs
    detour -- which a cap of zero minutes then forbids.
    """
    await add(
        api_client,
        organizer_event,
        person("Sam", "driver", role="driver", seats_available=3, max_detour_minutes=0),
    )
    await add(api_client, organizer_event, person("Bo", "west"))

    job = await optimize(api_client, organizer_event)

    async with engine.connect() as conn:
        reasons = (
            await conn.execute(
                text("select reason from unassigned_participants where solution_id = :s"),
                {"s": job["solution_id"]},
            )
        ).scalars()

    assert set(reasons) == {"detour_exceeded"}


async def test_an_empty_roster_cannot_be_optimized(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    await optimize(api_client, organizer_event, expect=422)


async def test_optimizing_requires_the_organizer_token(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, _ = organizer_event

    response = await api_client.post(f"/v1/events/{public_id}/optimizations", json={})

    assert response.status_code == 401


async def test_an_unknown_algorithm_is_rejected(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """CP-SAT is a measuring instrument, never a user request (docs/design.md 8.3)."""
    await seed_roster(api_client, organizer_event)

    await optimize(api_client, organizer_event, expect=422, json={"algorithm": "cpsat"})


async def test_re_optimizing_an_unchanged_event_reuses_the_solution(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """The fingerprint's whole purpose: an untouched event re-solves instantly, as 200 not 202."""
    await seed_roster(api_client, organizer_event)
    first = await optimize(api_client, organizer_event)

    second = await optimize(api_client, organizer_event, expect=200)

    assert second["job_id"] == first["job_id"]
    assert second["solution_id"] == first["solution_id"]


async def test_changing_the_roster_forces_a_fresh_solve(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """The version moved, so the old fingerprint match no longer applies."""
    await seed_roster(api_client, organizer_event)
    first = await optimize(api_client, organizer_event)

    await add(api_client, organizer_event, person("Dee", "north"))
    second = await optimize(api_client, organizer_event)

    assert second["job_id"] != first["job_id"]
    assert second["solution_id"] != first["solution_id"]
    assert second["input_version"] == 5


async def test_an_idempotency_key_replays_the_same_job(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """Defence in depth against a double-tapped button, independent of the fingerprint."""
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)
    keyed = {**headers, "Idempotency-Key": "11111111-1111-1111-1111-111111111111"}

    first = await api_client.post(f"/v1/events/{public_id}/optimizations", headers=keyed, json={})
    second = await api_client.post(f"/v1/events/{public_id}/optimizations", headers=keyed, json={})

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["job_id"] == first.json()["job_id"]


async def test_concurrent_optimize_requests_produce_one_job(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """`one_active_job_per_event` is the enforcement; the API only translates it to 409.

    Whether a loser sees 409 or the winner's already-finished solution depends on how far the winner
    got, so what is asserted is the invariant, not the status mix: exactly one job exists, and no
    caller is left without an answer.
    """
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)

    responses = await asyncio.gather(
        *(
            api_client.post(f"/v1/events/{public_id}/optimizations", headers=headers, json={})
            for _ in range(4)
        )
    )

    codes = sorted(response.status_code for response in responses)
    assert codes.count(202) == 1, codes
    assert all(code in (200, 202, 409) for code in codes), codes

    async with engine.connect() as conn:
        jobs = (
            await conn.execute(
                text(
                    "select count(*) from optimization_jobs j join events e on e.id = j.event_id"
                    " where e.public_id = :p"
                ),
                {"p": public_id},
            )
        ).scalar_one()
    assert jobs == 1


async def test_a_job_can_be_polled(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    response = await api_client.get(
        f"/v1/events/{public_id}/optimizations/{job['job_id']}", headers=headers
    )

    assert response.status_code == 200
    assert response.json() == job


async def test_a_job_of_another_event_is_not_reachable(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)
    other_id, other_headers = await other_event(api_client)

    response = await api_client.get(
        f"/v1/events/{other_id}/optimizations/{job['job_id']}", headers=other_headers
    )

    assert response.status_code == 404


async def test_cancelling_a_finished_job_leaves_it_alone(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """Cancellation is cooperative; there is nothing to stop about a succeeded job."""
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)
    job = await optimize(api_client, organizer_event)

    response = await api_client.delete(
        f"/v1/events/{public_id}/optimizations/{job['job_id']}", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["cancel_requested"] is False


async def test_request_weights_override_the_event_and_are_recorded(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """A past job stays reproducible after the event's settings change, so params holds them."""
    await seed_roster(api_client, organizer_event)

    job = await optimize(
        api_client, organizer_event, json={"weights": {"vehicle": 1.0, "drive_time": 2.0}}
    )

    assert job["weights"]["vehicle"] == 1.0
    assert job["weights"]["drive_time"] == 2.0
    assert job["weights"]["unassigned"] == 100_000.0, "unset weights keep the solver's default"


async def test_event_weights_are_used_when_the_request_omits_them(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    await api_client.patch(
        f"/v1/events/{public_id}", headers=headers, json={"weights": {"passenger_ride_time": 9.0}}
    )
    await seed_roster(api_client, organizer_event)

    job = await optimize(api_client, organizer_event)

    assert job["weights"]["passenger_ride_time"] == 9.0


async def test_different_weights_are_a_different_problem(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """Weights are in the fingerprint, so re-solving with new ones must not reuse the old answer."""
    await seed_roster(api_client, organizer_event)
    first = await optimize(api_client, organizer_event)

    second = await optimize(api_client, organizer_event, json={"weights": {"vehicle": 5.0}})

    assert second["job_id"] != first["job_id"]


async def test_a_cancelled_participant_is_left_out_of_the_solve(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """Cancelled rows are neither routed nor reported unassigned -- they are not on the roster."""
    public_id, headers = organizer_event
    roster = await seed_roster(api_client, organizer_event)
    await api_client.delete(
        f"/v1/events/{public_id}/participants/{roster['north']['id']}", headers=headers
    )

    job = await optimize(api_client, organizer_event)

    async with engine.connect() as conn:
        routed = (
            await conn.execute(
                text(
                    "select s.participant_id from route_stops s"
                    " join routes r on r.id = s.route_id where r.solution_id = :s"
                ),
                {"s": job["solution_id"]},
            )
        ).scalars()
        unassigned = (
            await conn.execute(
                text("select participant_id from unassigned_participants where solution_id = :s"),
                {"s": job["solution_id"]},
            )
        ).scalars()

    absent = roster["north"]["id"]
    assert absent not in {str(p) for p in routed}
    assert absent not in {str(p) for p in unassigned}
