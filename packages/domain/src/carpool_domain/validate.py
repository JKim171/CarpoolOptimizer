"""Feasibility checking.

Solvers are allowed to be heuristic about quality; they are never allowed to be wrong about
feasibility. Every solver's output goes through `validate`, and the property tests assert it comes
back empty for arbitrary generated instances (docs/design.md 9).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum

from .models import ProblemInstance, Route, Solution, outbound_schedule
from .objective import route_metrics


@dataclass(frozen=True, slots=True)
class Violation:
    code: str
    detail: str
    participant_id: str | None = None
    driver_id: str | None = None


class Constraint(str, Enum):
    """The classes of rule a single route can break.

    Named as a closed set so that "why is this route infeasible" and "why could nobody take this
    rider" are answerable in the same vocabulary. `explain.unassigned_reason` reports one of these,
    and the storage layer maps it to its own column vocabulary -- the domain does not know what
    string a database column expects.
    """

    #: The nominated driver is a passenger.
    ROLE = "role"
    #: More riders than the driver has seats.
    SEATS = "seats"
    #: The route exceeds the driver's own detour cap.
    DETOUR = "detour"
    #: A pickup falls before someone's `earliest_departure`.
    TIME = "time"
    #: A rider is pinned to a different driver.
    PIN = "pin"


def violated_constraints(
    instance: ProblemInstance,
    route: Route,
    *,
    ignore: frozenset[Constraint] = frozenset(),
) -> frozenset[Constraint]:
    """Which classes of rule `route` breaks, ignoring the ones named.

    `ignore` is what makes a *diagnosis* possible rather than just a verdict: relaxing one class
    at a time and re-asking shows which rule is actually binding, which is what an organizer needs
    to be told (docs/design.md, `unassigned_participants.reason`).
    """
    driver = instance.participant(route.driver_id)
    broken: set[Constraint] = set()

    if Constraint.ROLE not in ignore and not driver.role.can_drive:
        broken.add(Constraint.ROLE)

    metrics = route_metrics(instance, route)
    if Constraint.SEATS not in ignore and metrics.seats_used > driver.seats:
        broken.add(Constraint.SEATS)
    if (
        Constraint.DETOUR not in ignore
        and driver.max_detour_seconds is not None
        and metrics.detour_seconds > driver.max_detour_seconds
    ):
        broken.add(Constraint.DETOUR)

    if Constraint.PIN not in ignore:
        for passenger_id in route.passengers:
            if instance.participant(passenger_id).pinned_driver_id not in (None, driver.id):
                broken.add(Constraint.PIN)
                break

    if Constraint.TIME not in ignore:
        pickups = outbound_schedule(instance, route)
        for participant_id in (route.driver_id, *route.outbound):
            participant = instance.participant(participant_id)
            if (
                participant.earliest_departure is not None
                and pickups[participant_id] < participant.earliest_departure
            ):
                broken.add(Constraint.TIME)
                break

    return frozenset(broken)


def route_feasible(
    instance: ProblemInstance,
    route: Route,
    *,
    ignore: frozenset[Constraint] = frozenset(),
) -> bool:
    """Whether one route is legal on its own.

    This is the single definition of per-route feasibility, used by the solvers while they search.
    `validate` below answers a different question -- whether a whole `Solution` is coherent, with a
    reportable message per problem -- and covers rules a single route cannot express, such as a
    participant assigned twice or left out entirely.
    """
    return not violated_constraints(instance, route, ignore=ignore)


def validate(instance: ProblemInstance, solution: Solution) -> list[Violation]:
    """Return every way `solution` breaks the rules. Empty list means feasible."""
    violations: list[Violation] = []
    seen: Counter[str] = Counter()

    for route in solution.routes:
        seen[route.driver_id] += 1
        for passenger in route.outbound:
            seen[passenger] += 1
        for passenger in route.inbound:
            # Riding both legs is one assignment, not two.
            if passenger not in route.outbound:
                seen[passenger] += 1
    for participant_id in solution.unassigned:
        seen[participant_id] += 1

    for participant_id, count in seen.items():
        if not instance.has(participant_id):
            violations.append(
                Violation("unknown_participant", "not part of this event", participant_id)
            )
        elif count > 1:
            violations.append(
                Violation("duplicate_assignment", f"assigned {count} times", participant_id)
            )
    # Someone who needs neither leg is arranging their own transport and is not part of the
    # carpool at all, so their absence from the solution is correct rather than a violation.
    needs_transport = {p.id for p in instance.participants if p.needs_outbound or p.needs_return}
    for participant_id in sorted(needs_transport - set(seen)):
        violations.append(
            Violation("missing_assignment", "neither routed nor listed unassigned", participant_id)
        )

    for route in solution.routes:
        if not instance.has(route.driver_id):
            continue
        driver = instance.participant(route.driver_id)
        metrics = route_metrics(instance, route)

        if not driver.role.can_drive:
            violations.append(
                Violation(
                    "driver_cannot_drive", f"role is {driver.role.value}", driver_id=driver.id
                )
            )
        if metrics.seats_used > driver.seats:
            violations.append(
                Violation(
                    "capacity_exceeded",
                    f"{metrics.seats_used} passengers in {driver.seats} seats",
                    driver_id=driver.id,
                )
            )
        if (
            driver.max_detour_seconds is not None
            and metrics.detour_seconds > driver.max_detour_seconds
        ):
            violations.append(
                Violation(
                    "detour_exceeded",
                    f"{metrics.detour_seconds}s exceeds cap of {driver.max_detour_seconds}s",
                    driver_id=driver.id,
                )
            )

        pickups = outbound_schedule(instance, route)
        for participant_id in (route.driver_id, *route.outbound):
            participant = instance.participant(participant_id)
            if (
                participant.earliest_departure is not None
                and pickups[participant_id] < participant.earliest_departure
            ):
                violations.append(
                    Violation(
                        "early_pickup",
                        f"pickup at {pickups[participant_id]} precedes "
                        f"{participant.earliest_departure}",
                        participant_id,
                        driver.id,
                    )
                )

        for participant_id in route.passengers:
            participant = instance.participant(participant_id)
            if participant.pinned_driver_id not in (None, driver.id):
                violations.append(
                    Violation(
                        "pin_violated",
                        f"pinned to {participant.pinned_driver_id}",
                        participant_id,
                        driver.id,
                    )
                )
            if participant_id in route.outbound and not participant.needs_outbound:
                violations.append(
                    Violation(
                        "leg_not_needed", "routed outbound but does not need it", participant_id
                    )
                )
            if participant_id in route.inbound and not participant.needs_return:
                violations.append(
                    Violation(
                        "leg_not_needed", "routed inbound but does not need it", participant_id
                    )
                )
            if participant.needs_outbound and participant_id not in route.outbound:
                violations.append(
                    Violation(
                        "leg_missing", "needs the outbound leg but is not on it", participant_id
                    )
                )
            if participant.needs_return and participant_id not in route.inbound:
                violations.append(
                    Violation(
                        "leg_missing", "needs the return leg but is not on it", participant_id
                    )
                )

    for participant in instance.participants:
        if (
            participant.latest_arrival is not None
            and participant.latest_arrival < instance.arrival_by
        ):
            violations.append(
                Violation(
                    "late_arrival",
                    f"must arrive by {participant.latest_arrival}, event arrives "
                    f"{instance.arrival_by}",
                    participant.id,
                )
            )
    return violations
