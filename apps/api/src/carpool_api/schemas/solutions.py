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
from typing import Any, Self

from pydantic import BaseModel

from carpool_api.models import RouteLeg


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


class UnassignedRead(BaseModel):
    participant_id: uuid.UUID
    display_name: str
    #: no_capacity | detour_exceeded | time_window | no_drivers
    reason: str


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
    created_at: datetime
    routes: list[RouteRead]
    unassigned: list[UnassignedRead]


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
            created_at=solution.created_at,
        )
