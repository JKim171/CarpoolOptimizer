"""Writing a solved `Solution` into the database (docs/design.md 5, 8.2).

The domain returns orderings; the tables store orderings *plus* derived times, because the results
screen and the participant view should not each re-derive them (CLAUDE.md). The derivation still
lives in the domain (`outbound_schedule` / `inbound_schedule`), so a matrix refresh recomputes ETAs
from the same code that produced them.

The two legs are written separately, with their own `seq` ordering, because they are sequenced
independently against an asymmetric matrix (docs/design.md 8.2). Under Week 2's haversine provider
the matrix is symmetric, so the return order comes out as the exact reverse of the outbound --
that is the provider's property, not a bug in the persistence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from carpool_api import models
from carpool_api.adapters.instance import LoadedInstance
from carpool_api.models import RouteLeg
from carpool_domain import (
    Constraint,
    Solution,
    evaluate,
    inbound_schedule,
    outbound_schedule,
    route_metrics,
    unassigned_reason,
)

#: The domain names the rule that bound; the column has its own vocabulary (docs/design.md 5).
#: `PIN` lands on `no_capacity` because the diagnosis only returns it once no relaxation admitted
#: the rider -- their nominated driver genuinely has no room, rather than there being no driver.
REASON_BY_CONSTRAINT = {
    Constraint.ROLE: "no_drivers",
    Constraint.SEATS: "no_capacity",
    Constraint.DETOUR: "detour_exceeded",
    Constraint.TIME: "time_window",
    Constraint.PIN: "no_capacity",
}


def _moment(epoch_seconds: int) -> datetime:
    """Epoch seconds back to an aware UTC timestamp. The column is `timestamptz`; a naive value here
    would be read as server-local time and shift every ETA."""
    return datetime.fromtimestamp(epoch_seconds, tz=UTC)


def _percentile(values: list[int], fraction: float) -> int:
    """Nearest-rank percentile. With two or three cars it is effectively the maximum, which is the
    honest answer for a sample that small rather than an interpolated fiction."""
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(fraction * len(ordered)))
    return ordered[index]


def solution_metrics(loaded: LoadedInstance, solution: Solution) -> tuple[float, dict[str, Any]]:
    """The objective value and the `metrics` payload (docs/design.md 5).

    `gap_to_bound` is null rather than zero: no lower bound is computed in v1, and a zero would read
    as "proven optimal", which greedy has no right to claim. CP-SAT fills it in the benchmark
    harness, never on a user request (docs/design.md 8.3).
    """
    breakdown = evaluate(loaded.instance, solution)
    detours = [route_metrics(loaded.instance, route).detour_seconds for route in solution.routes]
    metrics = {
        "drive_s": breakdown.drive_seconds,
        "vehicles": breakdown.vehicles,
        "passenger_ride_s": breakdown.passenger_ride_seconds,
        "driver_detour_s": breakdown.driver_detour_seconds,
        "p95_detour_s": _percentile(detours, 0.95),
        "unassigned": len(solution.unassigned),
        "churn": breakdown.churn,
        "gap_to_bound": None,
    }
    return breakdown.total, metrics


def build_solution_rows(
    event: models.Event,
    job: models.OptimizationJob,
    loaded: LoadedInstance,
    solution: Solution,
) -> models.Solution:
    """The full object graph for one solved job, ready to `session.add`.

    Built as one graph rather than several inserts so that the solution, its routes, its stops and
    its unassigned rows commit together -- a half-written solution is worse than none, and
    `one_active_solution_per_event` assumes a row is complete the moment it is visible.
    """
    objective_value, metrics = solution_metrics(loaded, solution)

    record = models.Solution(
        event_id=event.id,
        job_id=job.id,
        algorithm=job.algorithm,
        objective_value=objective_value,
        metrics=metrics,
        input_version=job.input_version,
        is_active=False,
    )

    for route in solution.routes:
        stop_metrics = route_metrics(loaded.instance, route)
        outbound_times = outbound_schedule(loaded.instance, route)
        inbound_times = inbound_schedule(loaded.instance, route)

        stops = [
            models.RouteStop(
                leg=RouteLeg.OUTBOUND,
                seq=index,
                participant_id=uuid.UUID(node_id),
                eta=_moment(outbound_times[node_id]),
            )
            for index, node_id in enumerate(route.outbound)
        ] + [
            models.RouteStop(
                leg=RouteLeg.RETURN,
                seq=index,
                participant_id=uuid.UUID(node_id),
                eta=_moment(inbound_times[node_id]),
            )
            for index, node_id in enumerate(route.inbound)
        ]

        record.routes.append(
            models.Route(
                driver_participant_id=uuid.UUID(route.driver_id),
                seats_used=stop_metrics.seats_used,
                total_distance_m=(
                    loaded.estimates.path_distance_m(route.outbound_path)
                    + loaded.estimates.path_distance_m(route.inbound_path)
                ),
                total_duration_s=stop_metrics.outbound_seconds + stop_metrics.inbound_seconds,
                detour_seconds=stop_metrics.detour_seconds,
                #: Geometry stays null until someone looks at the map: the directions quota binds
                #: long before the matrix quota does (docs/design.md 4.4).
                outbound_geometry=None,
                return_geometry=None,
                stops=stops,
            )
        )

    for node_id in solution.unassigned:
        record.unassigned.append(
            models.UnassignedParticipant(
                participant_id=uuid.UUID(node_id),
                reason=REASON_BY_CONSTRAINT[unassigned_reason(loaded.instance, solution, node_id)],
            )
        )

    return record
