"""The objective function (docs/design.md 8.1).

Everything is denominated in seconds so the weighted total stays interpretable: a weight of 600 on
`vehicle` means one fewer car is worth ten minutes of extra driving.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from .models import DESTINATION, NodeId, ProblemInstance, Route, Solution, TravelMatrix


@dataclass(frozen=True, slots=True)
class RouteMetrics:
    driver_id: str
    outbound_seconds: int
    inbound_seconds: int
    #: What this driver would spend making the round trip alone.
    direct_seconds: int
    #: Excess over `direct_seconds`, i.e. the cost of carrying anyone at all.
    detour_seconds: int
    passenger_ride_seconds: int
    #: Peak occupancy across the two legs -- what capacity actually has to accommodate.
    seats_used: int


@dataclass(frozen=True, slots=True)
class ObjectiveBreakdown:
    """Component-wise cost. Reported rather than collapsed to a scalar.

    The breakdown is what makes a solution explicable to an organizer ("this run used one more car
    to cut nine minutes of detour") and what makes a regression in one term visible in benchmarks.
    """

    drive_seconds: int
    vehicles: int
    passenger_ride_seconds: int
    driver_detour_seconds: int
    unassigned_weight: int
    churn: int
    total: float


def _cumulative(matrix: TravelMatrix, path: tuple[NodeId, ...]) -> dict[NodeId, int]:
    """Seconds elapsed from `path[0]` to each node."""
    elapsed = 0
    out = {path[0]: 0}
    for a, b in pairwise(path):
        elapsed += matrix.duration(a, b)
        out[b] = elapsed
    return out


def route_metrics(instance: ProblemInstance, route: Route) -> RouteMetrics:
    matrix = instance.matrix
    outbound_path, inbound_path = route.outbound_path, route.inbound_path
    outbound = matrix.path_duration(outbound_path)
    inbound = matrix.path_duration(inbound_path)

    # A passenger's time in the car: from pickup to the destination outbound, from the destination
    # to drop-off on the way back.
    out_cum = _cumulative(matrix, outbound_path)
    in_cum = _cumulative(matrix, inbound_path)
    ride = sum(outbound - out_cum[p] for p in route.outbound)
    ride += sum(in_cum[p] for p in route.inbound)

    direct = matrix.duration(route.driver_id, DESTINATION) + matrix.duration(
        DESTINATION, route.driver_id
    )
    return RouteMetrics(
        driver_id=route.driver_id,
        outbound_seconds=outbound,
        inbound_seconds=inbound,
        direct_seconds=direct,
        detour_seconds=max(0, outbound + inbound - direct),
        passenger_ride_seconds=ride,
        seats_used=max(len(route.outbound), len(route.inbound)),
    )


def churn(previous: Solution, current: Solution) -> int:
    """Passengers whose assigned driver changed between two solutions (docs/design.md 8.4).

    Counted only over people present in both, so newcomers and departures are not charged as
    disruption -- only genuine reshuffling of people who were already placed.
    """
    before = {p: route.driver_id for route in previous.routes for p in route.passengers}
    after = {p: route.driver_id for route in current.routes for p in route.passengers}
    return sum(1 for p, driver in after.items() if p in before and before[p] != driver)


def evaluate(
    instance: ProblemInstance, solution: Solution, *, previous: Solution | None = None
) -> ObjectiveBreakdown:
    metrics = [route_metrics(instance, r) for r in solution.routes]
    weights = instance.weights

    drive = sum(m.outbound_seconds + m.inbound_seconds for m in metrics)
    ride = sum(m.passenger_ride_seconds for m in metrics)
    detour = sum(m.detour_seconds for m in metrics)
    unassigned = sum(
        1 + instance.participant(p).priority for p in solution.unassigned if instance.has(p)
    )
    disruption = churn(previous, solution) if previous is not None else 0

    total = (
        weights.drive_time * drive
        + weights.vehicle * len(metrics)
        + weights.passenger_ride_time * ride
        + weights.driver_detour * detour
        + weights.unassigned * unassigned
        + weights.churn * disruption
    )
    return ObjectiveBreakdown(
        drive_seconds=drive,
        vehicles=len(metrics),
        passenger_ride_seconds=ride,
        driver_detour_seconds=detour,
        unassigned_weight=unassigned,
        churn=disruption,
        total=total,
    )
