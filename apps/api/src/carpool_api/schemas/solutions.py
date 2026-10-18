"""Solution payloads (docs/design.md 6, 6.2, 7).

The organizer's view, unredacted. A participant sees a different and much narrower thing -- their
own assignment, their driver's contact, co-riders' first names -- and that is a separate class added
with the participant principal -- never this one with fields conditionally removed (design 6.2).

A leg reports its stop ordering and each stop's ETA, which is exactly what `route_stops` holds. It
does **not** report when the driver leaves home, even though that is the first thing a driver asks:
the driver owns the route rather than being a stop on it, and their departure cannot be recovered
from the stored rows. It is the first pickup minus the home-to-first-pickup travel, a duration that
lives in the travel matrix, not in the database. Deriving it needs either the matrix at read time or
a column of its own, and both belong with the Week 4 routing adapter. Returning a guess would be a
number a driver plans around.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel

from carpool_api.models import RouteLeg

#: Where a solution's times and distances came from: road times from the routing provider, or
#: straight-line estimates when it could not answer (docs/design.md 4.4).
Travel = Literal["ors", "haversine"]


def travel_of(metrics: dict[str, Any]) -> Travel:
    """Read out of `metrics`, where the solve records it. A solution from before road times existed
    recorded nothing, and every one of those was solved on estimates."""
    return "ors" if metrics.get("travel") == "ors" else "haversine"


class StopRead(BaseModel):
    seq: int
    participant_id: uuid.UUID
    display_name: str
    #: Pickup time outbound, drop-off time on the return.
    eta: datetime
    pickup_address: str


class LegRead(BaseModel):
    """One leg of one car. The legs carry different orderings on purpose (docs/design.md 8.2)."""

    leg: RouteLeg
    #: In `seq` order. Empty when nobody rides this leg, which a `needs_return = false` roster
    #: produces legitimately.
    stops: list[StopRead]


class RouteRead(BaseModel):
    id: uuid.UUID
    driver_participant_id: uuid.UUID
    driver_name: str
    seats_used: int
    #: Both legs combined, in integer seconds and metres (CLAUDE.md).
    total_duration_s: int
    total_distance_m: int
    #: Versus this driver's own direct round trip.
    detour_seconds: int
    outbound: LegRead
    inbound: LegRead


class RouteGeometry(BaseModel):
    """One car's path along the roads, both legs (docs/design.md 7.5).

    Each leg is `[lng, lat]` pairs in driving order, or null when the provider could not draw it --
    the map then joins that leg's stops with straight lines, as it does before any geometry exists.
    """

    route_id: uuid.UUID
    #: Lists rather than tuples: the generated client widens a tuple to `number[][]` regardless.
    outbound: list[list[float]] | None
    inbound: list[list[float]] | None


class SolutionGeometry(BaseModel):
    """Road lines for every car in a solution. Separate from `SolutionRead` because filling it can
    cost provider requests, and the list of cars must never wait on that."""

    routes: list[RouteGeometry]


class UnassignedRead(BaseModel):
    participant_id: uuid.UUID
    display_name: str
    #: no_capacity | detour_exceeded | time_window | no_drivers | unroutable
    reason: str


class FarFromRoad(BaseModel):
    """A pickup the routing provider had to move a long way to reach a road -- usually an address
    that geocoded to the wrong place (docs/design.md 7.2)."""

    participant_id: uuid.UUID
    display_name: str
    snapped_m: int


class SolutionRead(BaseModel):
    """A full solution, as the results screen needs it."""

    id: uuid.UUID
    job_id: uuid.UUID
    algorithm: str
    objective_value: float
    metrics: dict[str, Any]
    is_active: bool
    #: `events.participants_version` at the time this was solved.
    input_version: int
    #: True when the roster has changed since: the solution still describes a real arrangement, but
    #: not the current one (docs/design.md 5.1).
    is_stale: bool
    #: "haversine" means every time and distance in this answer is a straight-line estimate. Its own
    #: field rather than left in `metrics`, which is untyped on the wire, because the results
    #: screen has to say so.
    travel: Travel
    created_at: datetime
    routes: list[RouteRead]
    unassigned: list[UnassignedRead]
    #: Furthest first. Empty on estimates, which snap nothing.
    far_from_road: list[FarFromRoad]


class SolutionSummary(BaseModel):
    """One entry in the history list. Deliberately without routes -- an organizer comparing runs
    wants the shape of each answer, not every stop in all of them."""

    id: uuid.UUID
    job_id: uuid.UUID
    algorithm: str
    objective_value: float
    metrics: dict[str, Any]
    is_active: bool
    input_version: int
    is_stale: bool
    travel: Travel
    created_at: datetime

    @classmethod
    def of(cls, solution: Any, *, current_version: int) -> Self:
        return cls(
            id=solution.id,
            job_id=solution.job_id,
            algorithm=solution.algorithm,
            objective_value=solution.objective_value,
            metrics=solution.metrics,
            is_active=solution.is_active,
            input_version=solution.input_version,
            is_stale=solution.input_version < current_version,
            travel=travel_of(solution.metrics),
            created_at=solution.created_at,
        )
