"""Synthetic instance generation for tests and benchmarks (docs/design.md 8.5).

Instances are fully determined by their seed, so a benchmark result is reproducible and a property
test failure can be replayed exactly. Travel times come from the haversine fallback, which means
the generator never touches the network and the benchmark suite runs offline.

The three spatial distributions exist because they stress the solvers differently: uniform has no
structure to exploit, clustered rewards grouping neighbours, and radial -- riders strung along
corridors leading to the venue -- is the shape campus and school events actually take.
"""

from __future__ import annotations

import math
import random
from enum import StrEnum

from .models import (
    DESTINATION,
    Location,
    NodeId,
    ObjectiveWeights,
    Participant,
    ProblemInstance,
    Role,
    haversine_matrix,
)


class Distribution(StrEnum):
    UNIFORM = "uniform"
    CLUSTERED = "clustered"
    RADIAL = "radial"


#: Central Madison, Wisconsin -- roughly the geography the first real events will happen in.
DEFAULT_DESTINATION = Location(43.0731, -89.4012)

#: Arbitrary fixed instant; only differences between times are ever meaningful.
DEFAULT_ARRIVAL = 1_700_000_000

_METERS_PER_DEGREE_LAT = 111_320.0
#: Fraction of participants who could drive but are willing to ride instead. These are where
#: vehicle-count savings come from, so an instance without any is unrealistically rigid.
_FLEXIBLE_SHARE = 0.15


def _offset(origin: Location, north_m: float, east_m: float) -> Location:
    lat = origin.lat + north_m / _METERS_PER_DEGREE_LAT
    lng = origin.lng + east_m / (_METERS_PER_DEGREE_LAT * math.cos(math.radians(origin.lat)))
    return Location(lat, lng)


def _polar(origin: Location, radius_m: float, angle: float) -> Location:
    return _offset(origin, radius_m * math.sin(angle), radius_m * math.cos(angle))


def _points(
    rng: random.Random, destination: Location, n: int, radius_m: float, distribution: Distribution
) -> list[Location]:
    if distribution is Distribution.UNIFORM:
        # sqrt keeps the density even across the disc rather than piling up at the centre.
        return [
            _polar(destination, radius_m * math.sqrt(rng.random()), rng.uniform(0, math.tau))
            for _ in range(n)
        ]

    if distribution is Distribution.CLUSTERED:
        centres = [
            _polar(destination, radius_m * math.sqrt(rng.random()), rng.uniform(0, math.tau))
            for _ in range(max(2, n // 12))
        ]
        spread = radius_m / 6
        return [
            _offset(rng.choice(centres), rng.gauss(0, spread), rng.gauss(0, spread))
            for _ in range(n)
        ]

    corridors = [i * math.tau / max(3, min(8, n // 8)) for i in range(max(3, min(8, n // 8)))]
    return [
        _polar(
            destination,
            radius_m * math.sqrt(rng.random()),
            rng.choice(corridors) + rng.gauss(0, 0.15),
        )
        for _ in range(n)
    ]


def generate_instance(
    *,
    n: int,
    driver_ratio: float = 0.35,
    distribution: Distribution = Distribution.CLUSTERED,
    seed: int = 0,
    radius_km: float = 8.0,
    destination: Location = DEFAULT_DESTINATION,
    arrival_by: int = DEFAULT_ARRIVAL,
    weights: ObjectiveWeights | None = None,
    max_detour_seconds: int | None = None,
) -> ProblemInstance:
    """Build a reproducible synthetic instance of `n` participants."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if not 0.0 < driver_ratio <= 1.0:
        raise ValueError("driver_ratio must be in (0, 1]")

    rng = random.Random(seed)
    locations = _points(rng, destination, n, radius_km * 1000, distribution)

    drivers = max(1, round(n * driver_ratio))
    flexible = round((n - drivers) * _FLEXIBLE_SHARE)

    participants: list[Participant] = []
    for index, location in enumerate(locations):
        if index < drivers:
            role, seats = Role.DRIVER, rng.choice((2, 3, 4))
        elif index < drivers + flexible:
            role, seats = Role.EITHER, rng.choice((2, 3, 4))
        else:
            role, seats = Role.PASSENGER, 0
        participants.append(
            Participant(
                id=f"p{index:04d}",
                location=location,
                role=role,
                seats=seats,
                max_detour_seconds=max_detour_seconds if role.can_drive else None,
            )
        )

    nodes: dict[NodeId, Location] = {p.id: p.location for p in participants}
    nodes[DESTINATION] = destination
    return ProblemInstance(
        destination=destination,
        arrival_by=arrival_by,
        participants=tuple(participants),
        matrix=haversine_matrix(nodes),
        weights=weights if weights is not None else ObjectiveWeights(),
    )
