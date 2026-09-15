"""Objective weights as a payload (docs/design.md 8.1).

Weights live in `events.settings` so that an organizer can bias an event toward "fewest cars" or
"least inconvenience" -- which makes the objective a product feature rather than a constant buried
in the solver. A request may override them for one job, in which case the effective set is recorded
in `optimization_jobs.params`, so a past job stays reproducible after the event's settings change.

Every weight is in **seconds-equivalent**, which is what keeps them readable: `vehicle = 600` says
"one fewer car is worth ten minutes of extra driving", and that is how a coordinator at a
parking-constrained venue actually thinks. Defaults are read off `ObjectiveWeights` rather than
retyped, so the API cannot drift from the solver's own idea of a sensible baseline; a test asserts
the two carry the same fields.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from carpool_domain import ObjectiveWeights

_DEFAULTS = ObjectiveWeights()


class Weights(BaseModel):
    """All non-negative: a negative weight would pay the objective to do the thing it names."""

    model_config = ConfigDict(extra="forbid")

    #: Total driving, both legs.
    drive_time: float = Field(default=_DEFAULTS.drive_time, ge=0)
    #: Charged once per car. Only bites when someone can choose whether to drive, which today means
    #: a roster using `either` (CLAUDE.md).
    vehicle: float = Field(default=_DEFAULTS.vehicle, ge=0)
    #: Passenger time in the car, summed. A utilitarian total, which by construction cannot see how
    #: unevenly that time is distributed (docs/design.md 8.2).
    passenger_ride_time: float = Field(default=_DEFAULTS.passenger_ride_time, ge=0)
    #: A driver's excess over their own direct round trip.
    driver_detour: float = Field(default=_DEFAULTS.driver_detour, ge=0)
    #: Large by design: leaving somebody without a ride must lose to almost any amount of driving.
    unassigned: float = Field(default=_DEFAULTS.unassigned, ge=0)
    #: Re-optimization only, and inert until a solver can steer by it (docs/design.md 8.4).
    churn: float = Field(default=_DEFAULTS.churn, ge=0)

    def to_domain(self) -> ObjectiveWeights:
        return ObjectiveWeights(**self.model_dump())

    @classmethod
    def from_domain(cls, weights: ObjectiveWeights) -> Self:
        return cls(
            drive_time=weights.drive_time,
            vehicle=weights.vehicle,
            passenger_ride_time=weights.passenger_ride_time,
            driver_detour=weights.driver_detour,
            unassigned=weights.unassigned,
            churn=weights.churn,
        )
