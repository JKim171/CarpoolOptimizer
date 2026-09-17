"""Optimization endpoints (docs/design.md 6, 4.2, 5.1).

**The contract is asynchronous; the executor is not, yet.** `POST` answers `202` with a job id and
a `GET` reports on it, exactly as they will once a separate worker exists. In Week 2 the solve
happens inside the request. Week 4 decides whether to split the worker out, and if it does, only the
executor moves -- this contract, and the frontend polling it, do not (docs/design.md 4.2, "This is a
decision point, not a foregone conclusion").

Three mechanisms keep repeat requests from doing repeat work, in increasing order of bluntness:

1. **`one_active_job_per_event`**, a partial unique index. Two requests racing cannot both enqueue;
   the loser's insert raises and becomes a `409` naming the job that won. No lock needed.
2. **`Idempotency-Key`**, when the client sends one. A retried request returns the original job.
3. **`input_fingerprint`.** A request whose problem is byte-identical to one already solved returns
   that solution without solving, which is what makes re-running an untouched event instant.

**(1) and (3) only compose if (3) is checked after the insert, and that is not obvious.** The index
covers jobs that are *in flight*; a job that has finished has left it. Since the job row is
committed before the solve runs, a winner spends most of its life neither protected by the index nor
yet visible to a fingerprint check made a moment earlier -- so a concurrent request can slip between
the two and enqueue a duplicate. `create_optimization` therefore asks "already solved?" again once
its insert has succeeded, which is the point at which the index guarantees no rival is in flight.
No lock closes this: the winner releases everything at that commit, before it does the work.

The job row is committed *before* the solve, and the outcome written after. That is the boundary a
worker would sit on, so keeping it here is what makes Week 4 a change of executor rather than a
rewrite.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from carpool_api.adapters.fingerprint import input_fingerprint
from carpool_api.adapters.instance import (
    LoadedInstance,
    MissingCoordinates,
    active_roster,
    build_instance,
)
from carpool_api.adapters.solutions import build_solution_rows
from carpool_api.auth import OrganizerEvent
from carpool_api.db import get_session
from carpool_api.errors import violates
from carpool_api.geo import latitude_of, longitude_of
from carpool_api.models import Event, JobStatus, OptimizationJob, Participant, Solution
from carpool_api.schemas.events import weights_of
from carpool_api.schemas.optimizations import JobConflict, JobRead, OptimizationCreate
from carpool_api.schemas.weights import Weights
from carpool_domain import Location, greedy, validate

router = APIRouter(prefix="/v1/events/{public_id}/optimizations", tags=["optimizations"])

Session = Annotated[AsyncSession, Depends(get_session)]

_IN_FLIGHT = (JobStatus.QUEUED, JobStatus.RUNNING)
_IN_FLIGHT_INDEX = "one_active_job_per_event"

#: Visibility timeout. Comfortably longer than any solve this box will run -- greedy on the 50-seat
#: cap is seconds -- because expiring a lease early on a job that is still working would let a
#: second solve start alongside the first.
LEASE_SECONDS = 300


async def _reclaim_expired_leases(session: AsyncSession, event_id: uuid.UUID) -> None:
    """Fail in-flight jobs whose lease has run out, so a crash cannot wedge an event forever.

    Without this, a process that dies mid-solve -- OOM on a 2 GB box, a deploy restart, a container
    restart -- leaves `status = running` with nothing left to finish it. `one_active_job_per_event`
    then answers `409` to *every* future optimization of that event, permanently, with no recovery
    path short of editing the database by hand.

    Every in-flight job carries a lease from the moment it is inserted, not from the moment it
    starts running, so the brief `queued` window is covered too.

    This runs in the caller's transaction and before the insert, so the rows it fails have already
    left the partial unique index by the time the new job is added.
    """
    await session.execute(
        update(OptimizationJob)
        .where(
            OptimizationJob.event_id == event_id,
            OptimizationJob.status.in_(_IN_FLIGHT),
            OptimizationJob.lease_expires_at.is_not(None),
            OptimizationJob.lease_expires_at < datetime.now(UTC),
        )
        .values(
            status=JobStatus.FAILED,
            error="lease expired; the process running this job did not finish",
            finished_at=datetime.now(UTC),
        )
    )


class _AlreadySolved(Exception):
    """Raised inside the insert savepoint to unwind it when this problem is already solved.

    An exception rather than a flag because the savepoint is a context manager: leaving it by
    raising is what discards the row that was just inserted.
    """

    def __init__(self, job: OptimizationJob) -> None:
        super().__init__("this input has already been solved")
        self.job = job


async def _already_solved(
    session: AsyncSession,
    event_id: uuid.UUID,
    fingerprint: bytes,
    input_version: int,
) -> OptimizationJob | None:
    """A finished job whose solution answers exactly this problem, if one exists.

    Both the fingerprint and the roster version have to match: the fingerprint says the problem is
    byte-identical, and the version says the roster has not moved since (docs/design.md 5.1).
    """
    found = await session.execute(
        select(OptimizationJob)
        .join(Solution, Solution.job_id == OptimizationJob.id)
        .where(
            OptimizationJob.event_id == event_id,
            OptimizationJob.status == JobStatus.SUCCEEDED,
            OptimizationJob.input_fingerprint == fingerprint,
            OptimizationJob.input_version == input_version,
        )
        .order_by(OptimizationJob.finished_at.desc())
    )
    return found.scalars().first()


async def _destination(session: AsyncSession, event: Event) -> Location:
    found = await session.execute(
        select(
            latitude_of(Event.destination_geog),
            longitude_of(Event.destination_geog),
        ).where(Event.id == event.id)
    )
    lat, lng = found.one()._tuple()
    return Location(lat=lat, lng=lng)


async def _solution_id_of(session: AsyncSession, job_id: uuid.UUID) -> uuid.UUID | None:
    found = await session.execute(select(Solution.id).where(Solution.job_id == job_id))
    return found.scalars().first()


async def _read(session: AsyncSession, job: OptimizationJob, public_id: str) -> JobRead:
    return JobRead.of(
        job,
        event_public_id=public_id,
        solution_id=await _solution_id_of(session, job.id),
    )


async def _load(
    session: AsyncSession, event: Event, weights: Weights
) -> tuple[LoadedInstance, list[Participant]]:
    """The instance to solve, and the rows it was built from (which the fingerprint needs)."""
    roster = await active_roster(session, event)
    if not roster:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="an event needs at least one active participant to optimize",
        )
    destination = await _destination(session, event)
    try:
        loaded = build_instance(event, roster, destination, weights=weights)
    except MissingCoordinates as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return loaded, [row for row, _, _ in roster]


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobRead,
    responses={409: {"model": JobConflict}},
)
async def create_optimization(
    event: OrganizerEvent,
    session: Session,
    response: Response,
    payload: OptimizationCreate | None = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JobRead | JSONResponse:
    """Enqueue -- and, for now, immediately run -- an optimization.

    `202` means a job was created. `200` means an existing one is being returned instead: an
    idempotent retry, or a fingerprint matching an instance already solved. The body is identical
    either way, so a client that polls `job_id` need not distinguish them.
    """
    request = payload or OptimizationCreate()
    weights = request.weights or weights_of(event)
    event_id, public_id = event.id, event.public_id
    input_version = event.participants_version

    loaded, rows = await _load(session, event, weights)
    fingerprint = input_fingerprint(event, rows, algorithm=request.algorithm, weights=weights)

    if idempotency_key is not None:
        replayed = await session.execute(
            select(OptimizationJob).where(
                OptimizationJob.event_id == event_id,
                OptimizationJob.idempotency_key == idempotency_key,
            )
        )
        if (existing := replayed.scalar_one_or_none()) is not None:
            response.status_code = status.HTTP_200_OK
            return await _read(session, existing, public_id)

    if (solved := await _already_solved(session, event_id, fingerprint, input_version)) is not None:
        response.status_code = status.HTTP_200_OK
        return await _read(session, solved, public_id)

    # Before the insert, not after a 409: a wedged event has to heal on the next attempt rather
    # than stay wedged until someone notices.
    await _reclaim_expired_leases(session, event_id)

    job = OptimizationJob(
        event_id=event_id,
        status=JobStatus.QUEUED,
        algorithm=request.algorithm,
        params={"weights": weights.model_dump()},
        input_fingerprint=fingerprint,
        input_version=input_version,
        idempotency_key=idempotency_key,
        # Leased from insertion, so the queued window is covered as well as the running one.
        lease_expires_at=datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS),
    )
    try:
        # A savepoint, not the whole transaction: a conflict has to leave the session usable, so
        # that the winning job's id can still be read and reported.
        async with session.begin_nested():
            session.add(job)
            await session.flush()
            # Ask again, now that the insert has gone through. This is the check that actually
            # closes the race, and the earlier one is only a fast path.
            #
            # The reasoning: this insert succeeding *proves* no job was in flight for this event at
            # that instant, because `one_active_job_per_event` would have rejected it. So any job
            # that could have solved this same problem already reached a terminal state, and a
            # terminal state means committed -- which this statement, on a fresh read-committed
            # snapshot taken after the insert, is guaranteed to see.
            #
            # Checking only beforehand leaves a window no lock can close: the winner commits its
            # job and *then* solves, releasing anything it held, so the job it owns flips from
            # in-flight to succeeded while a concurrent request is between its check and its
            # insert. That request then finds nothing to reuse and nothing to collide with, and
            # a second job gets created for an identical roster -- a `202` where the contract
            # promises `200`, and in Week 4 a second ORS matrix call against a 500/day quota.
            # CI caught exactly this on 2026-09-17.
            duplicate = await _already_solved(session, event_id, fingerprint, input_version)
            if duplicate is not None:
                # Unwinds the savepoint, so the job just inserted never existed.
                raise _AlreadySolved(duplicate)
    except _AlreadySolved as hit:
        response.status_code = status.HTTP_200_OK
        return await _read(session, hit.job, public_id)
    except IntegrityError as exc:
        if not violates(exc, _IN_FLIGHT_INDEX):
            raise
        in_flight = await session.execute(
            select(OptimizationJob.id).where(
                OptimizationJob.event_id == event_id,
                OptimizationJob.status.in_(_IN_FLIGHT),
            )
        )
        existing_id = in_flight.scalars().first()
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=JobConflict(
                detail="an optimization is already in flight for this event",
                existing_job_id=existing_id,
            ).model_dump(mode="json"),
        )

    await session.commit()
    await _run(session, event, job)
    return await _read(session, job, public_id)


async def _run(session: AsyncSession, event: Event, job: OptimizationJob) -> None:
    """Solve the committed job and record the outcome, success or failure.

    The instance is rebuilt here rather than handed in, because the roster is read *after* the job
    row exists -- so what gets solved is what a worker claiming this job would have loaded.

    The solver runs in a worker thread. It is CPU-bound and pure, and running it on the event loop
    would stall every other request in the process, `/healthz` included -- which would turn a slow
    solve into a container restart (docs/design.md 4.2). It does not make solves parallel; it keeps
    one from blocking everything else.
    """
    job_id = job.id
    weights = Weights.model_validate(job.params.get("weights") or {})

    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(UTC)
    job.attempt += 1
    # Extended from the start of the solve rather than from insertion, so the timeout measures the
    # work rather than the queueing.
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
    await session.commit()

    try:
        loaded, _ = await _load(session, event, weights)
        solution = await asyncio.to_thread(greedy.solve, loaded.instance)
        violations = validate(loaded.instance, solution)
        if violations:
            # A solver may be heuristic about quality and never about feasibility (CLAUDE.md), so an
            # infeasible answer is a bug to surface, not a result to hand an organizer.
            raise RuntimeError(
                "solver produced an infeasible solution: "
                + "; ".join(f"{v.code}({v.participant_id or v.driver_id})" for v in violations)
            )
        session.add(build_solution_rows(event, job, loaded, solution))
        job.status = JobStatus.SUCCEEDED
        job.finished_at = datetime.now(UTC)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        # Re-fetched rather than reused: the rollback expired every instance in the session, and
        # touching a stale attribute in async SQLAlchemy raises instead of quietly reloading.
        failed = await session.get(OptimizationJob, job_id)
        if failed is not None:
            failed.status = JobStatus.FAILED
            failed.error = f"{type(exc).__name__}: {exc}"[:2000]
            failed.finished_at = datetime.now(UTC)
            await session.commit()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="the optimization failed; the job carries the error",
        ) from exc


async def _job_of_event(session: AsyncSession, job_id: uuid.UUID, event: Event) -> OptimizationJob:
    """Scoped by event, so a guessed job id on another event is a 404 rather than a read."""
    found = await session.execute(
        select(OptimizationJob).where(
            OptimizationJob.id == job_id,
            OptimizationJob.event_id == event.id,
        )
    )
    job = found.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such job")
    return job


@router.get("/{job_id}", response_model=JobRead)
async def get_optimization(
    job_id: uuid.UUID,
    event: OrganizerEvent,
    session: Session,
) -> JobRead:
    """Poll a job (docs/design.md 4.3 -- polling, not SSE, in v1).

    Nested under the event rather than at the bare `/v1/optimizations/{job_id}` of docs/design.md 6:
    an organizer token is scoped to an event, so the path must name the event for the dependency to
    authorize it at all. A flat path would make the job id itself the credential.
    """
    return await _read(session, await _job_of_event(session, job_id, event), event.public_id)


@router.delete("/{job_id}", response_model=JobRead)
async def cancel_optimization(
    job_id: uuid.UUID,
    event: OrganizerEvent,
    session: Session,
) -> JobRead:
    """Request cancellation. Cooperative, by design (docs/design.md 6.3).

    This sets `cancel_requested`; a worker checks it between solver iterations and exits cleanly.
    Killing a worker mid-transaction is not safe, and pretending a `DELETE` does it is a common
    mistake. A finished job is returned untouched: there is nothing left to stop, and rewriting its
    status would destroy the record of what happened.
    """
    job = await _job_of_event(session, job_id, event)
    if job.status in _IN_FLIGHT:
        job.cancel_requested = True
        await session.flush()
    read = await _read(session, job, event.public_id)
    await session.commit()
    return read
