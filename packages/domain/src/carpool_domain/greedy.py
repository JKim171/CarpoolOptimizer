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

from collections.abc import Callable, Iterable, Iterator, Mapping

from .models import DESTINATION, ProblemInstance, Role, Route, Solution
from .objective import evaluate, route_metrics
from .sequence import resequence
from .validate import route_feasible

#: Riders are only offered to the nearest few cars. Beyond that the insertion is never competitive,
#: and considering every car makes construction quadratic in the size of the event.
DEFAULT_CANDIDATE_DRIVERS = 10


def route_cost(instance: ProblemInstance, route: Route) -> float:
    """Weighted cost of one route, excluding the per-vehicle charge."""
    m = route_metrics(instance, route)
    w = instance.weights
    return (
        w.drive_time * (m.outbound_seconds + m.inbound_seconds)
        + w.passenger_ride_time * m.passenger_ride_seconds
        + w.driver_detour * m.detour_seconds
    )


def _positions(sequence: tuple[str, ...], rider: str) -> Iterator[tuple[str, ...]]:
    for i in range(len(sequence) + 1):
        yield (*sequence[:i], rider, *sequence[i:])


#: Prices one route for insertion. Large neighbourhood search passes a memoized one.
RouteCost = Callable[[ProblemInstance, Route], float]


def best_insertion(
    instance: ProblemInstance, route: Route, rider: str, *, cost: RouteCost = route_cost
) -> tuple[Route, float] | None:
    """Cheapest feasible way to add `rider` to `route`, with its marginal cost, or None."""
    participant = instance.participant(rider)
    # Occupancy does not depend on the order of the stops, so a car with no seat left on a leg the
    # rider needs refuses every position. Checking that once here, rather than in the feasibility
    # check of each would-be winner below, is most of the time a seat-short event takes to solve.
    seats = instance.participant(route.driver_id).seats
    if (participant.needs_outbound and len(route.outbound) >= seats) or (
        participant.needs_return and len(route.inbound) >= seats
    ):
        return None
    base = cost(instance, route)
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
            delta = cost(instance, candidate) - base
            # Pricing is cheaper than checking feasibility, so only a would-be winner is checked.
            if (best is None or delta < best[1]) and route_feasible(instance, candidate):
                best = (candidate, delta)
    return best


def seat_short(instance: ProblemInstance) -> bool:
    """Fewer seats than riders, so someone is left out whatever a solver does."""
    seats = sum(p.seats for p in instance.participants if p.role.can_drive)
    riders = sum(
        1
        for p in instance.participants
        if p.role is not Role.DRIVER and (p.needs_outbound or p.needs_return)
    )
    return seats < riders


#: Where a rider would go as things stand: the driver, their car with the rider in it, and the
#: price. A flexible rider's own new car is offered with themselves as the driver.
Offer = tuple[str, Route, float]


def seat_cheapest_first(
    routes: dict[str, Route],
    riders: Iterable[str],
    offer: Callable[[str], Offer | None],
    *,
    scale: Mapping[str, float] | None = None,
) -> list[str]:
    """Seat `riders` into `routes` one at a time, always whichever is cheapest to seat next, and
    return whoever is left without a seat.

    `offer` prices one rider against `routes` as they stand. `scale`, when given, multiplies each
    rider's price before the cheapest is chosen; large neighbourhood search passes random factors,
    so that successive rebuilds leave out different people.
    """
    offers = {r: offer(r) for r in riders}
    while offers:
        seatable = [
            (o[2] * (scale[r] if scale is not None else 1.0), r)
            for r, o in offers.items()
            if o is not None
        ]
        if not seatable:
            return sorted(offers)
        _, rider = min(seatable)
        chosen = offers.pop(rider)
        assert chosen is not None
        driver, route, _ = chosen
        opened = driver not in routes
        routes[driver] = route
        # Only offers into the car that changed are stale -- or, when a car was opened, every
        # offer, since the new car may be nearer than any that was considered. Offers into other
        # cars still stand: their cars did not change.
        for other, standing in offers.items():
            if opened or (standing is not None and standing[0] == driver):
                offers[other] = offer(other)
    return []


def _offer(
    instance: ProblemInstance, routes: dict[str, Route], rider: str, candidate_drivers: int
) -> Offer | None:
    """The cheapest place for `rider` among the nearest open cars, or a car of their own."""
    candidates = sorted(
        routes.values(),
        key=lambda r: (instance.matrix.duration(rider, r.driver_id), r.driver_id),
    )[:candidate_drivers]
    best: Offer | None = None
    for route in candidates:
        insertion = best_insertion(instance, route, rider)
        if insertion is not None and (best is None or insertion[1] < best[2]):
            best = (route.driver_id, insertion[0], insertion[1])

    # A flexible rider can drive instead of riding. Opening a car costs the per-vehicle charge
    # *plus that car's own round trip* -- charging only the former makes a new car look nearly
    # free and leaves every vehicle half empty.
    solo = Route(rider)
    if instance.participant(rider).role.can_drive and route_feasible(instance, solo):
        solo_cost = instance.weights.vehicle + route_cost(instance, solo)
        if best is None or best[2] > solo_cost:
            return (rider, solo, solo_cost)
    return best


def solve(
    instance: ProblemInstance, *, candidate_drivers: int = DEFAULT_CANDIDATE_DRIVERS
) -> Solution:
    """Assign every rider to a car, or record why they could not be.

    Riders are seated furthest from the venue first. When there are fewer seats than riders, that
    order spends the last seats on the riders dearest to carry, so a second construction seats
    whoever is cheapest next instead, and the cheaper of the two answers is returned.
    """
    furthest = _construct(instance, candidate_drivers, cheapest=False)
    if not seat_short(instance):
        return furthest
    cheapest = _construct(instance, candidate_drivers, cheapest=True)
    return (
        cheapest
        if evaluate(instance, cheapest).total < evaluate(instance, furthest).total
        else furthest
    )


def _construct(instance: ProblemInstance, candidate_drivers: int, *, cheapest: bool) -> Solution:
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
    # to fit and the easy ones would otherwise consume the capacity they need -- unless `cheapest`.
    pinned = [p for p in riders if p.pinned_driver_id is not None]
    flexible = sorted(
        (p for p in riders if p.pinned_driver_id is None),
        key=lambda p: (-instance.matrix.duration(p.id, DESTINATION), p.id),
    )

    unassigned: list[str] = []
    for rider in pinned:
        target = rider.pinned_driver_id
        assert target is not None
        if (
            target not in routes
            and instance.has(target)
            and instance.participant(target).role.can_drive
        ):
            routes[target] = Route(target)
        existing = routes.get(target)
        insertion = best_insertion(instance, existing, rider.id) if existing else None
        if insertion is None:
            unassigned.append(rider.id)
        else:
            routes[target] = insertion[0]

    # A flexible rider may already be driving, because someone is pinned to their car.
    free = [p.id for p in flexible if p.id not in routes]
    if cheapest:
        unassigned += seat_cheapest_first(
            routes, sorted(free), lambda r: _offer(instance, routes, r, candidate_drivers)
        )
    else:
        for rider_id in free:
            offer = _offer(instance, routes, rider_id, candidate_drivers)
            if offer is None:
                unassigned.append(rider_id)
            else:
                routes[offer[0]] = offer[1]

    final: list[Route] = []
    for _, route in sorted(routes.items()):
        tidied = resequence(instance, route)
        # Resequencing minimizes drive plus ride time, which under a heavy ride weight can lengthen
        # the drive enough to break a detour cap. Keep the original ordering when that happens.
        final.append(tidied if route_feasible(instance, tidied) else route)
    return Solution(routes=tuple(final), unassigned=tuple(unassigned))
