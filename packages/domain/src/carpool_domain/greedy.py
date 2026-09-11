"""Greedy insertion assignment (docs/design.md 8.3).

The baseline solver, and the one that ships first. Its contract is availability rather than
quality: it always returns a feasible solution, quickly, for any instance. Quality is the job of
the algorithms above it in the ladder -- and those reuse this module, because the "recreate" half
of large neighborhood search *is* greedy insertion.

Construction inserts each rider at the cheapest feasible position, then every route is resequenced
exactly (see `sequence`). Evaluating a full Held-Karp ordering for every candidate insertion would
be several orders of magnitude slower for no better result.
"""

from __future__ import annotations

from collections.abc import Iterator

from .models import DESTINATION, ProblemInstance, Role, Route, Solution, outbound_schedule
from .objective import route_metrics
from .sequence import resequence

#: Riders are only offered to the nearest few cars. Beyond that the insertion is never competitive,
#: and considering every car makes construction quadratic in the size of the event.
DEFAULT_CANDIDATE_DRIVERS = 10


def _route_cost(instance: ProblemInstance, route: Route) -> float:
    """Weighted cost of one route, excluding the per-vehicle charge."""
    m = route_metrics(instance, route)
    w = instance.weights
    return (
        w.drive_time * (m.outbound_seconds + m.inbound_seconds)
        + w.passenger_ride_time * m.passenger_ride_seconds
        + w.driver_detour * m.detour_seconds
    )


def _feasible(instance: ProblemInstance, route: Route) -> bool:
    driver = instance.participant(route.driver_id)
    if not driver.role.can_drive:
        return False
    m = route_metrics(instance, route)
    if m.seats_used > driver.seats:
        return False
    if driver.max_detour_seconds is not None and m.detour_seconds > driver.max_detour_seconds:
        return False
    for passenger_id in route.passengers:
        if instance.participant(passenger_id).pinned_driver_id not in (None, driver.id):
            return False
    pickups = outbound_schedule(instance, route)
    for participant_id in (route.driver_id, *route.outbound):
        participant = instance.participant(participant_id)
        if (
            participant.earliest_departure is not None
            and pickups[participant_id] < participant.earliest_departure
        ):
            return False
    return True


def _positions(sequence: tuple[str, ...], rider: str) -> Iterator[tuple[str, ...]]:
    for i in range(len(sequence) + 1):
        yield (*sequence[:i], rider, *sequence[i:])


def _best_insertion(
    instance: ProblemInstance, route: Route, rider: str
) -> tuple[Route, float] | None:
    """Cheapest feasible way to add `rider` to `route`, with its marginal cost, or None."""
    participant = instance.participant(rider)
    base = _route_cost(instance, route)
    outbound_options = (
        list(_positions(route.outbound, rider)) if participant.needs_outbound else [route.outbound]
    )
    inbound_options = (
        list(_positions(route.inbound, rider)) if participant.needs_return else [route.inbound]
    )

    best: tuple[Route, float] | None = None
    for outbound in outbound_options:
        for inbound in inbound_options:
            candidate = Route(route.driver_id, outbound, inbound)
            if not _feasible(instance, candidate):
                continue
            delta = _route_cost(instance, candidate) - base
            if best is None or delta < best[1]:
                best = (candidate, delta)
    return best


def solve(
    instance: ProblemInstance, *, candidate_drivers: int = DEFAULT_CANDIDATE_DRIVERS
) -> Solution:
    """Assign every rider to a car, or record why they could not be."""
    routes: dict[str, Route] = {
        p.id: Route(p.id) for p in instance.participants if p.role is Role.DRIVER
    }
    riders = [
        p
        for p in instance.participants
        if p.role is not Role.DRIVER and (p.needs_outbound or p.needs_return)
    ]

    # Pins are constraints, not preferences: they claim their seat before greed can spend it.
    # Everyone else is placed furthest-from-the-venue first, because distant riders are the hardest
    # to fit and the easy ones would otherwise consume the capacity they need.
    pinned = [p for p in riders if p.pinned_driver_id is not None]
    flexible = sorted(
        (p for p in riders if p.pinned_driver_id is None),
        key=lambda p: (-instance.matrix.duration(p.id, DESTINATION), p.id),
    )

    unassigned: list[str] = []
    for rider in [*pinned, *flexible]:
        target = rider.pinned_driver_id
        if target is not None:
            if (
                target not in routes
                and instance.has(target)
                and instance.participant(target).role.can_drive
            ):
                routes[target] = Route(target)
            existing = routes.get(target)
            insertion = _best_insertion(instance, existing, rider.id) if existing else None
            if insertion is None:
                unassigned.append(rider.id)
            else:
                routes[target] = insertion[0]
            continue

        candidates = sorted(
            routes.values(),
            key=lambda r: (instance.matrix.duration(rider.id, r.driver_id), r.driver_id),
        )[:candidate_drivers]
        best: tuple[str, Route, float] | None = None
        for route in candidates:
            insertion = _best_insertion(instance, route, rider.id)
            if insertion is not None and (best is None or insertion[1] < best[2]):
                best = (route.driver_id, insertion[0], insertion[1])

        # A flexible rider can drive instead of riding. Opening a car costs the per-vehicle charge
        # *plus that car's own round trip* -- charging only the former makes a new car look nearly
        # free and leaves every vehicle half empty.
        solo = Route(rider.id)
        can_open = rider.role.can_drive and _feasible(instance, solo)
        solo_cost = instance.weights.vehicle + _route_cost(instance, solo)
        if can_open and (best is None or best[2] > solo_cost):
            routes[rider.id] = solo
        elif best is not None:
            routes[best[0]] = best[1]
        else:
            unassigned.append(rider.id)

    final: list[Route] = []
    for _, route in sorted(routes.items()):
        tidied = resequence(instance, route)
        # Resequencing minimizes drive plus ride time, which under a heavy ride weight can lengthen
        # the drive enough to break a detour cap. Keep the original ordering when that happens.
        final.append(tidied if _feasible(instance, tidied) else route)
    return Solution(routes=tuple(final), unassigned=tuple(unassigned))
