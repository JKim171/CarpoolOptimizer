"""Exact route sequencing (docs/design.md 8.2).

Given a driver and a fixed set of passengers, decide the order to collect them on the way to the
event and the order to drop them off afterwards. Because every route ends at one shared
destination, this is a shortest Hamiltonian *path* rather than a tour, and for realistic car sizes
Held-Karp solves it exactly in microseconds. Route sequencing in this system is therefore never
approximate -- only the assignment is.

The DP minimizes drive time *and* passenger ride time together, which it can do because ride time
decomposes over edges: traversing an edge costs `w_drive * d + w_ride * onboard * d`, and `onboard`
is determined by the subset already visited -- exactly the DP state.

The return leg is sequenced independently rather than assumed to be the outbound reversed. Under a
symmetric matrix reversal is provably optimal, so this would be wasted work -- but real routing
matrices are asymmetric (one-way streets, turn restrictions), and only an independent pass can
exploit that. See docs/design.md 8.2.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from itertools import pairwise

from .models import DESTINATION, NodeId, ProblemInstance, Route, TravelMatrix

#: Above this many stops the DP is abandoned for a heuristic. No passenger car reaches it; the
#: bound exists so a generated benchmark instance with an implausible vehicle cannot blow up.
MAX_EXACT_STOPS = 12

#: Occupancy while traversing the edge that departs after `visited` stops have been served.
OnboardFn = Callable[[int], int]


def _leg_cost(
    matrix: TravelMatrix,
    path: tuple[NodeId, ...],
    w_drive: float,
    w_ride: float,
    onboard: OnboardFn,
) -> float:
    total = 0.0
    for index, (a, b) in enumerate(pairwise(path)):
        total += matrix.duration(a, b) * (w_drive + w_ride * onboard(index))
    return total


def _held_karp(
    matrix: TravelMatrix,
    origin: NodeId,
    terminus: NodeId,
    stops: Sequence[NodeId],
    w_drive: float,
    w_ride: float,
    onboard: OnboardFn,
) -> tuple[NodeId, ...]:
    """Minimum-cost ordering of `stops` on a path from `origin` to `terminus`. O(2^n * n^2)."""
    n = len(stops)
    full = (1 << n) - 1
    inf = float("inf")
    best = [[inf] * n for _ in range(1 << n)]
    came_from = [[-1] * n for _ in range(1 << n)]

    departure_rate = w_drive + w_ride * onboard(0)
    for k in range(n):
        best[1 << k][k] = matrix.duration(origin, stops[k]) * departure_rate

    for mask in range(1 << n):
        rate = w_drive + w_ride * onboard(mask.bit_count())
        for j in range(n):
            if not mask >> j & 1:
                continue
            cost_so_far = best[mask][j]
            if cost_so_far == inf:
                continue
            for k in range(n):
                if mask >> k & 1:
                    continue
                candidate = cost_so_far + matrix.duration(stops[j], stops[k]) * rate
                target = mask | 1 << k
                if candidate < best[target][k]:
                    best[target][k] = candidate
                    came_from[target][k] = j

    final_rate = w_drive + w_ride * onboard(n)
    last = min(
        range(n), key=lambda j: best[full][j] + matrix.duration(stops[j], terminus) * final_rate
    )

    order: list[NodeId] = []
    mask, j = full, last
    while j != -1:
        order.append(stops[j])
        mask, j = mask ^ 1 << j, came_from[mask][j]
    order.reverse()
    return tuple(order)


def _nearest_neighbour_then_2opt(
    matrix: TravelMatrix,
    origin: NodeId,
    terminus: NodeId,
    stops: Sequence[NodeId],
    w_drive: float,
    w_ride: float,
    onboard: OnboardFn,
) -> tuple[NodeId, ...]:
    """Heuristic fallback for implausibly large vehicles. See MAX_EXACT_STOPS."""
    remaining = list(stops)
    order: list[NodeId] = []
    current = origin
    while remaining:
        nxt = min(remaining, key=lambda s: matrix.duration(current, s))
        remaining.remove(nxt)
        order.append(nxt)
        current = nxt

    def cost(candidate: list[NodeId]) -> float:
        return _leg_cost(matrix, (origin, *candidate, terminus), w_drive, w_ride, onboard)

    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                trial = order[:i] + order[i : j + 1][::-1] + order[j + 1 :]
                if cost(trial) < cost(order) - 1e-9:
                    order, improved = trial, True
    return tuple(order)


def _sequence(
    instance: ProblemInstance,
    origin: NodeId,
    terminus: NodeId,
    stops: Sequence[NodeId],
    onboard: OnboardFn,
) -> tuple[NodeId, ...]:
    if len(stops) <= 1:
        return tuple(stops)
    weights = instance.weights
    solver = _held_karp if len(stops) <= MAX_EXACT_STOPS else _nearest_neighbour_then_2opt
    # A driver's detour is their route time minus their solo commute, and the commute is fixed once
    # the driver is chosen. Detour therefore varies linearly with drive time, so the two weights
    # combine into a single effective rate -- without which sequencing would optimize a different
    # objective than the one the solution is scored against.
    return solver(
        instance.matrix,
        origin,
        terminus,
        stops,
        weights.drive_time + weights.driver_detour,
        weights.passenger_ride_time,
        onboard,
    )


def sequence_outbound(
    instance: ProblemInstance, driver_id: str, passengers: Sequence[str]
) -> tuple[str, ...]:
    """Pickup order from the driver's home to the destination.

    Occupancy grows as the car fills: after `visited` pickups, `visited` passengers are aboard.
    """
    return _sequence(instance, driver_id, DESTINATION, passengers, lambda visited: visited)


def sequence_inbound(
    instance: ProblemInstance, driver_id: str, passengers: Sequence[str]
) -> tuple[str, ...]:
    """Drop-off order from the destination back to the driver's home.

    Occupancy shrinks as the car empties: the passenger dropped last rides longest. Note that a
    *sum* of ride times cannot express fairness between passengers, only total burden -- see the
    fairness note in docs/design.md 8.2.
    """
    total = len(passengers)
    return _sequence(instance, DESTINATION, driver_id, passengers, lambda visited: total - visited)


def resequence(instance: ProblemInstance, route: Route) -> Route:
    """Return `route` with both legs optimally ordered. Never worsens the objective."""
    return Route(
        driver_id=route.driver_id,
        outbound=sequence_outbound(instance, route.driver_id, route.outbound),
        inbound=sequence_inbound(instance, route.driver_id, route.inbound),
    )
