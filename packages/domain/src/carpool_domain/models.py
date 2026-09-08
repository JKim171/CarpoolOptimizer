"""Core domain types.

Pure data and pure functions only -- no database, no HTTP, no clock. See docs/design.md 4.1.

Every duration is an integer number of seconds; every point in time is epoch seconds. Keeping one
unit throughout is what lets the objective weights in `ObjectiveWeights` stay interpretable.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from itertools import pairwise

#: Sentinel node for the shared event destination. Every route begins or ends here.
DESTINATION = "__destination__"

NodeId = str

EARTH_RADIUS_M = 6_371_000.0


class Role(str, Enum):
    """How a participant gets to the event.

    `EITHER` -- has a car but is willing to ride instead -- is implemented and tested but not
    offered by the MVP roster UI. It is dormant by decision, not dead code; see docs/design.md 2.3.
    While no participant carries it the driver set is fixed, which makes the `vehicle` objective
    weight inert.
    """

    DRIVER = "driver"
    PASSENGER = "passenger"
    EITHER = "either"

    @property
    def can_drive(self) -> bool:
        return self in (Role.DRIVER, Role.EITHER)


@dataclass(frozen=True, slots=True)
class Location:
    lat: float
    lng: float


@dataclass(frozen=True, slots=True)
class Participant:
    """One person attending the event.

    Drivers are participants like anyone else: `location` is where their car starts, which makes it
    the origin of their outbound route and the terminus of their return (docs/design.md 8.2).
    """

    id: str
    location: Location
    role: Role = Role.PASSENGER
    #: Passengers this person can carry, excluding themselves.
    seats: int = 0
    #: Generic scarcity weight. Higher means costlier to leave without a ride (docs/design.md 2.2).
    priority: int = 0
    earliest_departure: int | None = None
    latest_arrival: int | None = None
    max_detour_seconds: int | None = None
    pinned_driver_id: str | None = None
    needs_outbound: bool = True
    needs_return: bool = True

    def __post_init__(self) -> None:
        if self.seats < 0:
            raise ValueError(f"participant {self.id!r}: seats must be >= 0")
        if self.priority < 0:
            raise ValueError(f"participant {self.id!r}: priority must be >= 0")


@dataclass(frozen=True, slots=True)
class ObjectiveWeights:
    """Objective weights, all in seconds-equivalent so the total stays readable.

    `vehicle = 600.0` reads directly as "one fewer car is worth ten minutes of extra driving" --
    which is how a coordinator at a parking-constrained venue actually thinks about it.
    """

    drive_time: float = 1.0
    vehicle: float = 600.0
    passenger_ride_time: float = 0.5
    driver_detour: float = 1.0
    unassigned: float = 100_000.0
    churn: float = 0.0


class TravelMatrix:
    """Directed travel durations in seconds between nodes.

    Directed rather than symmetric because real road networks are: one-way streets and turn
    restrictions make `a -> b` and `b -> a` genuinely different, and the return leg depends on it.
    """

    __slots__ = ("_durations",)

    def __init__(self, durations: Mapping[tuple[NodeId, NodeId], int]) -> None:
        self._durations = dict(durations)

    def duration(self, origin: NodeId, destination: NodeId) -> int:
        if origin == destination:
            return 0
        try:
            return self._durations[(origin, destination)]
        except KeyError:
            raise KeyError(f"no travel duration for {origin!r} -> {destination!r}") from None

    def path_duration(self, nodes: tuple[NodeId, ...]) -> int:
        return sum(self.duration(a, b) for a, b in pairwise(nodes))


def haversine_meters(a: Location, b: Location) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlng = math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def haversine_matrix(
    nodes: Mapping[NodeId, Location],
    *,
    speed_kmh: float = 32.0,
    road_factor: float = 1.3,
) -> TravelMatrix:
    """Straight-line fallback matrix (docs/design.md 4.4).

    Used for unit tests and as the provider of last resort. `road_factor` crudely accounts for the
    fact that roads are not straight lines; 32 km/h is a reasonable urban average.
    """
    mps = speed_kmh * 1000 / 3600
    return TravelMatrix(
        {
            (a, b): int(haversine_meters(la, lb) * road_factor / mps)
            for a, la in nodes.items()
            for b, lb in nodes.items()
            if a != b
        }
    )


@dataclass(frozen=True, slots=True)
class ProblemInstance:
    """A fully specified optimization problem. Contains no identifiers from the storage layer."""

    destination: Location
    #: Everyone must be at the destination by this time; schedules are computed backward from it.
    arrival_by: int
    participants: tuple[Participant, ...]
    matrix: TravelMatrix
    weights: ObjectiveWeights = field(default_factory=ObjectiveWeights)
    _index: dict[str, Participant] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        index = {p.id: p for p in self.participants}
        if len(index) != len(self.participants):
            raise ValueError("duplicate participant ids")
        if DESTINATION in index:
            raise ValueError(f"{DESTINATION!r} is reserved and cannot be a participant id")
        object.__setattr__(self, "_index", index)

    def participant(self, participant_id: str) -> Participant:
        return self._index[participant_id]

    def has(self, participant_id: str) -> bool:
        return participant_id in self._index

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self._index)


@dataclass(frozen=True, slots=True)
class Route:
    """One driver's assignment, as an ordering rather than a schedule.

    Times are derived (see `schedule`), never stored here -- so a route stays valid when the travel
    matrix is refreshed, and two solvers producing the same ordering compare equal.

    `inbound` is sequenced separately from `outbound` rather than assumed to be its reverse. Under
    a symmetric matrix reversal is exactly optimal, but real routing matrices are asymmetric --
    one-way streets and turn restrictions -- so the return earns its own pass (docs/design.md 8.2).
    """

    driver_id: str
    outbound: tuple[str, ...] = ()
    inbound: tuple[str, ...] = ()

    @property
    def passengers(self) -> frozenset[str]:
        return frozenset(self.outbound) | frozenset(self.inbound)

    @property
    def outbound_path(self) -> tuple[NodeId, ...]:
        return (self.driver_id, *self.outbound, DESTINATION)

    @property
    def inbound_path(self) -> tuple[NodeId, ...]:
        return (DESTINATION, *self.inbound, self.driver_id)


@dataclass(frozen=True, slots=True)
class Solution:
    routes: tuple[Route, ...] = ()
    unassigned: tuple[str, ...] = ()

    def driver_of(self, participant_id: str) -> str | None:
        for route in self.routes:
            if participant_id == route.driver_id or participant_id in route.passengers:
                return route.driver_id
        return None


def schedule_forward(
    matrix: TravelMatrix, path: tuple[NodeId, ...], depart_at: int
) -> dict[NodeId, int]:
    """Arrival time at each node along `path`, given a departure time from `path[0]`."""
    t = depart_at
    times = {path[0]: t}
    for a, b in pairwise(path):
        t += matrix.duration(a, b)
        times[b] = t
    return times


def schedule_backward(
    matrix: TravelMatrix, path: tuple[NodeId, ...], arrive_by: int
) -> dict[NodeId, int]:
    """Arrival time at each node along `path`, given a required arrival at `path[-1]`.

    This is the natural direction for an outbound leg: the deadline is fixed and the departure time
    is what falls out of it. Return legs schedule forward from the event end instead.
    """
    return schedule_forward(matrix, path, arrive_by - matrix.path_duration(path))
