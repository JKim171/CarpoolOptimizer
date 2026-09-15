"""Solution endpoints (docs/design.md 6, 5.1).

History, one solution in full, and activation. Organizer principal only; the participant's redacted
`GET .../assignment` arrives with the participant principal (docs/design.md 6.2).

**Activation is the act that makes a solution the answer**, and exactly one per event can hold that
status -- enforced by `one_active_solution_per_event`, a partial unique index, so two activation
requests racing cannot produce two live answers. The API deactivates and activates in one
transaction, which is what keeps that index satisfied at every point a concurrent reader could look.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from carpool_api.auth import OrganizerEvent
from carpool_api.db import get_session
from carpool_api.models import Event, Participant, Route, RouteLeg, Solution
from carpool_api.schemas.solutions import (
    LegRead,
    RouteRead,
    SolutionRead,
    SolutionSummary,
    StopRead,
    UnassignedRead,
)

router = APIRouter(prefix="/v1/events/{public_id}/solutions", tags=["solutions"])

Session = Annotated[AsyncSession, Depends(get_session)]


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
