"""Solution endpoints (docs/design.md 6, 5.1).

History, one solution in full, and activation. Organizer principal only; the participant's redacted
`GET .../assignment` arrives with the participant principal (docs/design.md 6.2).

**Activation is the act that makes a solution the answer**, and exactly one per event can hold that
status -- enforced by `one_active_solution_per_event`, a partial unique index, so two activation
requests racing cannot produce two live answers. The API deactivates and activates in one
transaction, which is what keeps that index satisfied at every point a concurrent reader could look.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from carpool_api.adapters.directions import Coordinate, OrsDirections
from carpool_api.adapters.travel import TravelUnavailable
from carpool_api.auth import OrganizerEvent
from carpool_api.config import Settings, get_settings
from carpool_api.db import get_session
from carpool_api.geo import latitude_of, line, longitude_of, simplified_geojson
from carpool_api.models import Event, Participant, Route, RouteLeg, Solution
from carpool_api.schemas.solutions import (
    LegRead,
    RouteGeometry,
    RouteRead,
    SolutionGeometry,
    SolutionRead,
    SolutionSummary,
    StopRead,
    UnassignedRead,
    travel_of,
)
from carpool_domain import Location

router = APIRouter(prefix="/v1/events/{public_id}/solutions", tags=["solutions"])

Session = Annotated[AsyncSession, Depends(get_session)]


def get_directions(settings: Annotated[Settings, Depends(get_settings)]) -> OrsDirections | None:
    """The Directions client, or None without a key -- every leg then stays straight lines. A
    dependency so tests can substitute one that makes no network call."""
    return OrsDirections(settings) if settings.ors_api_key else None


Directions = Annotated[OrsDirections | None, Depends(get_directions)]

#: About five metres: below what a line on a town-sized map can show, and enough to drop most of
#: the points a road line arrives with -- a 20-minute leg comes back as several hundred.
GEOMETRY_TOLERANCE_DEGREES = 0.00005

#: Directions requests in flight at once for one view. A whole 50-person event is about 30 legs,
#: inside the provider's 40 a minute; this only keeps one view from opening 30 connections at once.
DIRECTIONS_CONCURRENCY = 4


async def _names(session: AsyncSession, event: Event) -> dict[uuid.UUID, Participant]:
    """Every participant of the event, cancelled included.

    Cancelled ones are needed: a solution computed before somebody dropped out still names them, and
    rendering that solution must not fail because they are no longer on the roster.
    """
    found = await session.execute(select(Participant).where(Participant.event_id == event.id))
    return {row.id: row for row in found.scalars()}


async def _load(session: AsyncSession, event: Event, solution_id: uuid.UUID) -> Solution:
    found = await session.execute(
        select(Solution)
        .where(Solution.id == solution_id, Solution.event_id == event.id)
        .options(
            selectinload(Solution.routes).selectinload(Route.stops),
            selectinload(Solution.unassigned),
        )
    )
    solution = found.scalar_one_or_none()
    if solution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such solution")
    return solution


def _leg(route: Route, leg: RouteLeg, people: dict[uuid.UUID, Participant]) -> LegRead:
    """One leg's stop ordering, exactly as stored.

    The driver's own departure time is deliberately absent -- it is not recoverable from these rows;
    see the module docstring of `schemas/solutions.py`.
    """
    stops = sorted((stop for stop in route.stops if stop.leg is leg), key=lambda s: s.seq)
    return LegRead(
        leg=leg,
        stops=[
            StopRead(
                seq=stop.seq,
                participant_id=stop.participant_id,
                display_name=people[stop.participant_id].display_name,
                eta=stop.eta,
                pickup_address=people[stop.participant_id].pickup_address,
            )
            for stop in stops
        ],
    )


def _route(route: Route, people: dict[uuid.UUID, Participant]) -> RouteRead:
    driver = people[route.driver_participant_id]
    return RouteRead(
        id=route.id,
        driver_participant_id=route.driver_participant_id,
        driver_name=driver.display_name,
        seats_used=route.seats_used,
        total_duration_s=route.total_duration_s,
        total_distance_m=route.total_distance_m,
        detour_seconds=route.detour_seconds,
        outbound=_leg(route, RouteLeg.OUTBOUND, people),
        inbound=_leg(route, RouteLeg.RETURN, people),
    )


def _read(solution: Solution, people: dict[uuid.UUID, Participant], version: int) -> SolutionRead:
    return SolutionRead(
        id=solution.id,
        job_id=solution.job_id,
        algorithm=solution.algorithm,
        objective_value=solution.objective_value,
        metrics=solution.metrics,
        is_active=solution.is_active,
        input_version=solution.input_version,
        is_stale=solution.input_version < version,
        travel=travel_of(solution.metrics),
        created_at=solution.created_at,
        routes=[
            _route(route, people)
            for route in sorted(solution.routes, key=lambda r: str(r.driver_participant_id))
        ],
        unassigned=[
            UnassignedRead(
                participant_id=row.participant_id,
                display_name=people[row.participant_id].display_name,
                reason=row.reason,
            )
            for row in sorted(solution.unassigned, key=lambda r: str(r.participant_id))
        ],
    )


@router.get("", response_model=list[SolutionSummary])
async def list_solutions(event: OrganizerEvent, session: Session) -> list[SolutionSummary]:
    """Every solution for this event, newest first.

    History is kept rather than overwritten: comparing this week's answer with last week's is how an
    organizer judges whether a re-optimization was worth the disruption (docs/design.md 8.4).
    """
    found = await session.execute(
        select(Solution)
        .where(Solution.event_id == event.id)
        .order_by(Solution.created_at.desc(), Solution.id)
    )
    return [
        SolutionSummary.of(solution, current_version=event.participants_version)
        for solution in found.scalars()
    ]


@router.get("/{solution_id}", response_model=SolutionRead)
async def get_solution(
    solution_id: uuid.UUID,
    event: OrganizerEvent,
    session: Session,
) -> SolutionRead:
    solution = await _load(session, event, solution_id)
    return _read(solution, await _names(session, event), event.participants_version)


@router.post("/{solution_id}/activate", response_model=SolutionRead)
async def activate_solution(
    solution_id: uuid.UUID,
    event: OrganizerEvent,
    session: Session,
) -> SolutionRead:
    """Make this the event's live answer.

    Deactivating the incumbent and activating this one happen in one transaction, so
    `one_active_solution_per_event` is never momentarily violated and no reader ever sees two live
    answers or none. Activating the already-active solution is a no-op rather than an error.

    A stale solution can still be activated on purpose: the organizer may well prefer a known
    arrangement over re-solving an hour before the event. The response says it is stale; it does not
    refuse.
    """
    solution = await _load(session, event, solution_id)

    if not solution.is_active:
        await session.execute(
            update(Solution)
            .where(Solution.event_id == event.id, Solution.is_active)
            .values(is_active=False)
            .execution_options(synchronize_session=False)
        )
        await session.flush()
        solution.is_active = True
        await session.flush()

    read = _read(solution, await _names(session, event), event.participants_version)
    await session.commit()
    return read


async def _places(
    session: AsyncSession, event: Event
) -> tuple[dict[uuid.UUID, Location], Location]:
    """Where every participant is picked up, cancelled ones included, and the destination."""
    found = await session.execute(
        select(
            Participant.id,
            latitude_of(Participant.pickup_geog),
            longitude_of(Participant.pickup_geog),
        ).where(Participant.event_id == event.id, Participant.pickup_geog.is_not(None))
    )
    people = {pid: Location(lat=lat, lng=lng) for pid, lat, lng in found.all()}
    venue = await session.execute(
        select(latitude_of(Event.destination_geog), longitude_of(Event.destination_geog)).where(
            Event.id == event.id
        )
    )
    lat, lng = venue.one()._tuple()
    return people, Location(lat=lat, lng=lng)


def _waypoints(
    route: Route, leg: RouteLeg, people: dict[uuid.UUID, Location], destination: Location
) -> list[Location] | None:
    """The points this leg is driven through, in order, or None if any of them cannot be placed.

    A leg with no riders still has a line: the driver goes to the event and home again either way.
    """
    riders = [s.participant_id for s in sorted(route.stops, key=lambda s: s.seq) if s.leg is leg]
    ids = [route.driver_participant_id, *riders]
    if any(pid not in people for pid in ids):
        return None
    home, stops = people[route.driver_participant_id], [people[pid] for pid in riders]
    if leg is RouteLeg.OUTBOUND:
        return [home, *stops, destination]
    return [destination, *stops, home]


_COLUMN = {RouteLeg.OUTBOUND: "outbound_geometry", RouteLeg.RETURN: "return_geometry"}


def _coordinates(geojson: str | None) -> list[list[float]] | None:
    if geojson is None:
        return None
    return [[point[0], point[1]] for point in json.loads(geojson)["coordinates"]]


@router.get("/{solution_id}/geometry", response_model=SolutionGeometry)
async def get_solution_geometry(
    solution_id: uuid.UUID,
    event: OrganizerEvent,
    session: Session,
    directions: Directions,
) -> SolutionGeometry:
    """Every car's path along the roads, fetched the first time anyone asks and stored after.

    Lazily, because one solution costs about 30 Directions requests and the daily quota is 2,000
    (docs/design.md 4.4): fetching at solve time would spend it on answers nobody looks at. A leg
    the provider cannot draw comes back null and is asked for again on the next view; the map draws
    it straight in the meantime.
    """
    solution = await _load(session, event, solution_id)
    missing = [
        (route, leg)
        for route in solution.routes
        for leg in RouteLeg
        if getattr(route, _COLUMN[leg]) is None
    ]
    if missing and directions is not None:
        people, destination = await _places(session, event)
        slots = asyncio.Semaphore(DIRECTIONS_CONCURRENCY)

        async def fetch(route: Route, leg: RouteLeg) -> list[Coordinate] | None:
            waypoints = _waypoints(route, leg, people, destination)
            if waypoints is None:
                return None
            async with slots:
                try:
                    return await directions.line(waypoints)
                except TravelUnavailable:
                    return None

        lines = await asyncio.gather(*(fetch(route, leg) for route, leg in missing))
        for (route, leg), found in zip(missing, lines, strict=True):
            if found is not None:
                setattr(route, _COLUMN[leg], line(found))
        await session.commit()

    rows = await session.execute(
        select(
            Route.id,
            Route.driver_participant_id,
            simplified_geojson(Route.outbound_geometry, GEOMETRY_TOLERANCE_DEGREES),
            simplified_geojson(Route.return_geometry, GEOMETRY_TOLERANCE_DEGREES),
        ).where(Route.solution_id == solution.id)
    )
    return SolutionGeometry(
        routes=[
            RouteGeometry(
                route_id=route_id, outbound=_coordinates(outbound), inbound=_coordinates(inbound)
            )
            for route_id, _, outbound, inbound in sorted(rows.all(), key=lambda r: str(r[1]))
        ]
    )
