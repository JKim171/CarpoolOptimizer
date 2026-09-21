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
    got, so what is asserted is the invariant, not the status mix: **one job for one problem**, and
    no caller left without an answer.

    What makes it hold is the re-check *after* the insert in `create_optimization`. Without it the
    losers read "nothing solved yet", the winner commits its job and then finishes solving -- which
    takes it out of the partial index, since that only covers jobs still in flight -- and a loser's
    insert then succeeds, producing a second job for an identical roster.

    This failed in CI on 2026-09-17 and passes on a fast machine either way, which is the point:
    the window is real but narrow, so the assertion that matters is the job count, and the status
    mix is only checked for "everyone got a sensible answer".
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
    assert all(code in (200, 202, 409) for code in codes), codes
    # Exactly one caller may be told it created something. The rest were either refused (409) or
    # handed the winner's answer (200); which of those they get is a timing detail, and asserting
    # the mix would be asserting how fast the solve ran.
    assert codes.count(202) == 1, codes

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


async def test_a_slow_request_cannot_enqueue_a_duplicate_after_the_winner_finishes(
    api_client: AsyncClient,
    organizer_event: tuple[str, dict[str, str]],
    engine: AsyncEngine,
    monkeypatch,
) -> None:
    """The race above, made deterministic instead of left to timing.

    The defect needs a request to be *between* its "already solved?" check and its insert while the
    winner commits and finishes solving. On a fast machine that window is microseconds and the test
    above passes whether or not the bug is present -- which is exactly why CI caught this and local
    runs did not.

    Widening the window on purpose is what makes the assertion mean something. The delay goes into
    `_reclaim_expired_leases` because that is the step which genuinely sits in the gap, so this
    exercises the real ordering rather than a rearranged one.
    """
    from carpool_api.routes import optimizations

    original = optimizations._reclaim_expired_leases

    async def slow_reclaim(session, event_id):
        await original(session, event_id)
        await asyncio.sleep(0.4)

    monkeypatch.setattr(optimizations, "_reclaim_expired_leases", slow_reclaim)

    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)

    responses = await asyncio.gather(
        *(
            api_client.post(f"/v1/events/{public_id}/optimizations", headers=headers, json={})
            for _ in range(4)
        )
    )

    codes = sorted(response.status_code for response in responses)
    assert all(code in (200, 202, 409) for code in codes), codes
    assert codes.count(202) == 1, codes

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
    assert jobs == 1, "a second job was enqueued for an identical roster"


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


async def test_an_expired_lease_is_reclaimed_so_the_event_is_not_wedged(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """A crash mid-solve must not block the event from ever being optimized again.

    The failure this pins is not theoretical: the in-request executor commits `running` before
    solving, so a process that dies there -- OOM on a 2 GB box, a deploy restart -- leaves a row
    that `one_active_job_per_event` treats as in flight forever, and every later optimize of that
    event answers 409 with no recovery path short of editing the database.

    Simulated by backdating the lease rather than by killing a process, which is the same state.
    """
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into optimization_jobs"
                " (id, event_id, status, algorithm, params, input_fingerprint, input_version,"
                "  lease_expires_at, queued_at, started_at)"
                " select gen_random_uuid(), e.id, 'running', 'greedy', '{}'::jsonb,"
                " '\\x00'::bytea, 0,"
                " now() - interval '1 hour', now() - interval '2 hours',"
                " now() - interval '2 hours'"
                " from events e where e.public_id = :p"
            ),
            {"p": public_id},
        )

    # Without reclamation this is a 409.
    job = await optimize(api_client, organizer_event)
    assert job["status"] == "succeeded"

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "select j.status, j.error from optimization_jobs j"
                    " join events e on e.id = j.event_id where e.public_id = :p"
                    " order by j.queued_at"
                ),
                {"p": public_id},
            )
        ).all()

    assert [row[0] for row in rows] == ["failed", "succeeded"]
    assert "lease expired" in rows[0][1]


async def test_a_live_lease_still_blocks_a_second_job(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """The reclaim must not become a way around `one_active_job_per_event`.

    A lease that has NOT expired belongs to something that may still be working, so failing it
    would let two solves run against one event at once -- the exact race the partial unique index
    exists to prevent.
    """
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into optimization_jobs"
                " (id, event_id, status, algorithm, params, input_fingerprint, input_version,"
                "  lease_expires_at)"
                " select gen_random_uuid(), e.id, 'running', 'greedy', '{}'::jsonb,"
                " '\\x00'::bytea, 0,"
                " now() + interval '5 minutes'"
                " from events e where e.public_id = :p"
            ),
            {"p": public_id},
        )

    response = await api_client.post(
        f"/v1/events/{public_id}/optimizations", headers=headers, json={}
    )
    assert response.status_code == 409


async def test_a_new_job_carries_a_lease(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """Leased from insertion rather than from the start of the solve.

    The `queued` window is brief but real, and a process that dies inside it would otherwise leave
    a job with no lease for the reclaim to find.
    """
    public_id, _ = organizer_event
    await seed_roster(api_client, organizer_event)
    await optimize(api_client, organizer_event)

    async with engine.connect() as conn:
        lease = (
            await conn.execute(
                text(
                    "select j.lease_expires_at from optimization_jobs j"
                    " join events e on e.id = j.event_id where e.public_id = :p"
                ),
                {"p": public_id},
            )
        ).scalar_one()

    assert lease is not None


async def test_non_finite_weights_are_rejected(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """`json.loads` accepts `Infinity` and `NaN`; a bare float field would too.

    An `inf` weight used to pass validation and then fail on the JSONB write, turning a bad request
    into a 500. `NaN` was already rejected by `ge=0` -- only because comparisons against NaN are
    false, which is luck rather than a rule -- so both are pinned here.
    """
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)

    for token in ("Infinity", "-Infinity", "NaN"):
        response = await api_client.post(
            f"/v1/events/{public_id}/optimizations",
            headers={**headers, "content-type": "application/json"},
            content=f'{{"weights": {{"drive_time": {token}}}}}',
        )
        assert response.status_code == 422, (token, response.status_code)


async def test_an_absurdly_large_weight_is_rejected(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """A merely large finite weight reaches the same place `inf` does, via overflow in a sum."""
    public_id, headers = organizer_event
    await seed_roster(api_client, organizer_event)

    response = await api_client.post(
        f"/v1/events/{public_id}/optimizations",
        headers=headers,
        json={"weights": {"drive_time": 1e300}},
    )
    assert response.status_code == 422


async def test_solves_are_rate_limited_per_event(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], monkeypatch
) -> None:
    """Only a solve that creates a job is charged; a reused answer runs nothing, costs nothing."""
    from carpool_api.ratelimit import Rule

    monkeypatch.setattr(
        "carpool_api.routes.optimizations.SOLVES", Rule("solve", 1, 3600, "Too many optimizations")
    )
    await seed_roster(api_client, organizer_event)
    await optimize(api_client, organizer_event)
    # Unchanged roster: answered from the existing solution, and not refused.
    await optimize(api_client, organizer_event, expect=200)

    await add(api_client, organizer_event, person("Dee", "north"))
    refused = await optimize(api_client, organizer_event, expect=429)

    assert refused["detail"].startswith("Too many optimizations")
    # Another event has its own allowance.
    other = await other_event(api_client)
    await seed_roster(api_client, other)
    await optimize(api_client, other)


async def test_no_more_than_two_solves_run_at_once(api_client: AsyncClient, monkeypatch) -> None:
    """A burst queues for the two cores instead of every solve competing for them."""
    import threading
    import time

    from carpool_api.ratelimit import SOLVE_CONCURRENCY
    from carpool_domain import greedy

    real_solve = greedy.solve
    lock = threading.Lock()
    running = 0
    peak = 0

    def slow_solve(instance):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.2)
        with lock:
            running -= 1
        return real_solve(instance)

    monkeypatch.setattr(greedy, "solve", slow_solve)
    events = [await other_event(api_client) for _ in range(4)]
    for event in events:
        await seed_roster(api_client, event)

    await asyncio.gather(*(optimize(api_client, event) for event in events))

    assert peak == SOLVE_CONCURRENCY
