"""The example event on the public `/demo` page, emitted as a stable file.

The page shows a finished answer to someone who has not entered anything, which no real event can
do: a real event's page holds names and home addresses, so it sits behind an organizer token and is
kept out of search. This one is **generated** -- the synthetic instance generator, a fixed seed, and
the same solver and response models a real solve goes through -- so it is a real answer about
nobody, and the file can be committed (CLAUDE.md: fixtures are generated, never dumped).

The solution is shaped as `SolutionRead`, so the web app renders it with the same components as a
real result rather than a second implementation of the results screen. `test_demo.py` fails the
build when the committed file no longer matches what this produces, the same guard as the OpenAPI
contract. `make demo` regenerates it.

Usage: python -m carpool_api.demo [path]   (stdout when no path is given)
"""

from __future__ import annotations

import dataclasses
import math
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from carpool_api.adapters.instance import LoadedInstance
from carpool_api.adapters.solutions import solution_metrics
from carpool_api.adapters.travel import haversine_estimates
from carpool_api.contract import serialize
from carpool_api.models import ParticipantRole, RouteLeg
from carpool_api.schemas.solutions import LegRead, RouteRead, SolutionRead, StopRead
from carpool_domain import (
    DESTINATION,
    Location,
    NodeId,
    Role,
    greedy,
    haversine_meters,
    inbound_schedule,
    outbound_schedule,
    route_metrics,
    validate,
)
from carpool_domain.generate import Distribution, generate_instance

NAME = "Club tennis — Thursday practice"
VENUE_LABEL = "The practice courts"
#: West Madison, chosen so that every generated home within `RADIUS_KM` lands on dry land rather
#: than in Lake Mendota or Lake Wingra -- a pin in a lake reads as fake at a glance.
VENUE = Location(43.0465, -89.5045)
TIME_ZONE = "America/Chicago"
#: Thursday 15 October 2026, 6:00 pm Central. Only the clock time is shown.
ARRIVAL = 1_792_105_200
PRACTICE_SECONDS = 2 * 60 * 60

#: Picked by trying seeds: everyone gets a ride, every driver carries somebody, and the cars come
#: out at different sizes, which is what a real roster looks like.
SEED = 5
RADIUS_KM = 5.0
NAMES = (
    "Maya R.",
    "Theo K.",
    "Priya S.",
    "Jordan L.",
    "Sam W.",
    "Elena M.",
    "Marcus T.",
    "Hana Y.",
    "Diego F.",
    "Ava P.",
    "Noah B.",
    "Lena C.",
)

#: Every id in the file is derived from this, so regenerating produces the same bytes.
_NAMESPACE = uuid.UUID("6f1d2b1e-3c55-4c4e-9a8e-2f0d7c1b9a10")

#: About ten centimetres. Rounded so the committed file does not hinge on the last bit of a
#: platform's `cos`, which is not guaranteed to agree between the machine that wrote it and CI.
_PLACES = 6

_COMPASS = ("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest")


class DemoVenue(BaseModel):
    address: str
    lat: float
    lng: float


class DemoPerson(BaseModel):
    id: uuid.UUID
    display_name: str
    role: ParticipantRole
    lat: float
    lng: float


class DemoEvent(BaseModel):
    name: str
    venue: DemoVenue
    time_zone: str
    arrival_at: datetime
    ends_at: datetime
    people: list[DemoPerson]
    solution: SolutionRead


def _id(name: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, name)


def _moment(epoch_seconds: int) -> datetime:
    return datetime.fromtimestamp(epoch_seconds, tz=UTC)


def _whereabouts(location: Location) -> str:
    """Where someone lives, as a distance and a direction from the courts.

    In place of a street address, which a generated person does not have -- and inventing one would
    put a fictional family at a real front door.
    """
    miles = haversine_meters(VENUE, location) / 1609.344
    north = location.lat - VENUE.lat
    east = (location.lng - VENUE.lng) * math.cos(math.radians(VENUE.lat))
    bearing = math.degrees(math.atan2(east, north)) % 360
    return f"{miles:.1f} mi {_COMPASS[round(bearing / 45) % 8]} of the courts"


def build() -> DemoEvent:
    generated = generate_instance(
        n=len(NAMES),
        driver_ratio=0.34,
        distribution=Distribution.CLUSTERED,
        seed=SEED,
        radius_km=RADIUS_KM,
        destination=VENUE,
        arrival_by=ARRIVAL,
        event_duration_seconds=PRACTICE_SECONDS,
    )
    # The generator makes some riders `EITHER`, a role the roster UI does not offer (CLAUDE.md). The
    # example shows only what an organizer can actually enter.
    participants = tuple(
        dataclasses.replace(p, role=Role.PASSENGER, seats=0) if p.role is Role.EITHER else p
        for p in generated.participants
    )
    nodes: dict[NodeId, Location] = {p.id: p.location for p in participants}
    nodes[DESTINATION] = VENUE
    estimates = haversine_estimates(nodes)
    instance = dataclasses.replace(generated, participants=participants, matrix=estimates.matrix)

    solution = greedy.solve(instance)
    if violations := validate(instance, solution):
        raise ValueError(f"the demo solution is infeasible: {violations}")
    if solution.unassigned:
        raise ValueError("the demo should leave nobody without a ride; pick another seed")

    names = dict(zip((p.id for p in participants), NAMES, strict=True))
    whereabouts = {p.id: _whereabouts(p.location) for p in participants}

    def leg(kind: RouteLeg, order: tuple[str, ...], times: dict[NodeId, int]) -> LegRead:
        return LegRead(
            leg=kind,
            stops=[
                StopRead(
                    seq=index,
                    participant_id=_id(node),
                    display_name=names[node],
                    eta=_moment(times[node]),
                    pickup_address=whereabouts[node],
                )
                for index, node in enumerate(order)
            ],
        )

    routes = []
    for route in solution.routes:
        figures = route_metrics(instance, route)
        routes.append(
            RouteRead(
                id=_id(f"route:{route.driver_id}"),
                driver_participant_id=_id(route.driver_id),
                driver_name=names[route.driver_id],
                seats_used=figures.seats_used,
                total_duration_s=figures.outbound_seconds + figures.inbound_seconds,
                total_distance_m=(
                    estimates.path_distance_m(route.outbound_path)
                    + estimates.path_distance_m(route.inbound_path)
                ),
                detour_seconds=figures.detour_seconds,
                outbound=leg(RouteLeg.OUTBOUND, route.outbound, outbound_schedule(instance, route)),
                inbound=leg(RouteLeg.RETURN, route.inbound, inbound_schedule(instance, route)),
            )
        )

    objective_value, metrics = solution_metrics(
        LoadedInstance(instance=instance, estimates=estimates, rows={}), solution
    )
    return DemoEvent(
        name=NAME,
        venue=DemoVenue(address=VENUE_LABEL, lat=VENUE.lat, lng=VENUE.lng),
        time_zone=TIME_ZONE,
        arrival_at=_moment(instance.arrival_by),
        ends_at=_moment(instance.ends_at),
        people=[
            DemoPerson(
                id=_id(p.id),
                display_name=names[p.id],
                role=ParticipantRole.DRIVER if p.role is Role.DRIVER else ParticipantRole.PASSENGER,
                lat=round(p.location.lat, _PLACES),
                lng=round(p.location.lng, _PLACES),
            )
            for p in participants
        ],
        solution=SolutionRead(
            id=_id("solution"),
            job_id=_id("job"),
            algorithm="greedy",
            objective_value=objective_value,
            metrics=metrics,
            is_active=True,
            input_version=1,
            is_stale=False,
            created_at=_moment(instance.arrival_by - 24 * 60 * 60),
            routes=routes,
            unassigned=[],
        ),
    )


def render() -> str:
    return serialize(build().model_dump(mode="json"))


def main(argv: list[str]) -> int:
    text = render()
    if argv:
        Path(argv[0]).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
