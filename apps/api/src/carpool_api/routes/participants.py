"""Roster endpoints (docs/design.md 6, 5.1, 5.3).

Organizer principal only: in Model A the coordinator enters the whole roster, so there is no join
flow yet (docs/design.md 2.1).

Two invariants are worth reading before changing anything here.

**The 50-participant cap is made race-free by ordering, not by locking.** Every mutation bumps
`events.participants_version` *first*. That `UPDATE` takes the event row's lock, so two requests
racing for the last seat serialize behind it; counting active participants after the insert, in the
same transaction, is then a count nobody else can be changing. Two callers cannot both see 49.
There is no advisory lock and no `SELECT ... FOR UPDATE` anywhere in this module, and adding one
would be a sign the ordering above had been broken (docs/design.md 5.1).

**Cancelling is a status change, never a delete.** A participant row is a snapshot of one person's
participation, referenced by any solution already computed; deleting it would either break those
references or rewrite history (docs/design.md 5.3.1).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import Row, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from carpool_api.auth import OrganizerEvent
from carpool_api.db import get_session
from carpool_api.geo import latitude_of, longitude_of, point
from carpool_api.limits import MAX_ACTIVE_PARTICIPANTS
from carpool_api.models import (
    Event,
    EventStatus,
    GeocodeSource,
    Participant,
    ParticipantRole,
    ParticipantStatus,
)
from carpool_api.schemas.participants import (
    ParticipantCreate,
    ParticipantOrganizerRead,
    ParticipantPatch,
    ParticipantWritten,
    RosterRead,
)
from carpool_api.security import hash_token, new_token

router = APIRouter(prefix="/v1/events/{public_id}/participants", tags=["participants"])

Session = Annotated[AsyncSession, Depends(get_session)]

#: Participant, latitude, longitude -- the shape every read in this module selects.
_WITH_COORDINATES = (
    Participant,
    latitude_of(Participant.pickup_geog),
    longitude_of(Participant.pickup_geog),
)


def _read(row: Row[tuple[Participant, float, float]]) -> ParticipantOrganizerRead:
    """SQLAlchemy types `ST_Y`/`ST_X` as non-optional, but `pickup_geog` is nullable and the
    ordinates of a NULL point are NULL. That is the normal case from Week 4 on, for a participant
    whose coordinates come from the geocode cache rather than their own row -- which is why
    `ParticipantOrganizerRead.of` accepts `None`."""
    participant, lat, lng = row._tuple()
    return ParticipantOrganizerRead.of(participant, lat, lng)


def _require_open_roster(event: Event) -> None:
    """Roster writes stop when the event is locked -- that is what locking means.

    Event *details* stay editable while locked (see `routes/events.py`); it is the set of people the
    lock freezes, because a solution is only meaningful against a settled roster.
    """
    if event.status is EventStatus.LOCKED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the roster is locked; unlock the event to change it",
        )
    if event.status is EventStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an archived event cannot be changed",
        )


async def _bump_version(session: AsyncSession, event: Event) -> int:
    """Increment the roster version and return the new value.

    This is the lock. It is an `UPDATE` of the event row, so every concurrent roster mutation on the
    same event queues behind it for the rest of the transaction -- which is what makes the count in
    `_enforce_cap` trustworthy. Call it before touching participants, always.

    `synchronize_session=False` because the in-session `Event` object is deliberately left holding
    its old value: refreshing it would either emit another statement or mark it dirty, and the
    handler wants the returned number, not the object.
    """
    result = await session.execute(
        update(Event)
        .where(Event.id == event.id)
        .values(participants_version=Event.participants_version + 1)
        .returning(Event.participants_version)
        .execution_options(synchronize_session=False)
    )
    return result.scalar_one()


async def _active_count(session: AsyncSession, event: Event) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(Participant)
            .where(
                Participant.event_id == event.id,
                Participant.status == ParticipantStatus.ACTIVE,
            )
        )
    ).scalar_one()


async def _enforce_cap(session: AsyncSession, event: Event) -> None:
    """Reject the participant that would exceed the cap.

    Counted *after* the insert has been flushed, so the new row is included and the comparison is
    against the roster as it would actually be. Raising here abandons the transaction, which undoes
    the insert and the version bump together -- the caller sees no change at all, rather than a
    version that moved for a participant who was rejected.
    """
    if await _active_count(session, event) > MAX_ACTIVE_PARTICIPANTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"an event may have at most {MAX_ACTIVE_PARTICIPANTS} active participants",
        )


async def _load(session: AsyncSession, event: Event, participant_id: uuid.UUID) -> Participant:
    """One participant of this event, cancelled ones included -- 404 otherwise.

    Scoped by `event_id` rather than looked up by primary key alone: without it, an organizer's
    token would reach any participant row in the database whose id they could guess.
    """
    found = await session.execute(
        select(Participant).where(
            Participant.id == participant_id,
            Participant.event_id == event.id,
        )
    )
    participant = found.scalar_one_or_none()
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such participant")
    return participant


async def _validate_pin(
    session: AsyncSession,
    event: Event,
    participant_id: uuid.UUID | None,
    *,
    pinned_driver_id: uuid.UUID | None,
) -> None:
    """A pin must name an active participant of *this* event who can drive.

    The foreign key only guarantees that some participant row exists -- it cannot express "on the
    same event", and the solver would treat a cross-event pin as an unsatisfiable constraint and
    strand the rider. Checked after the version bump, so a concurrent edit cannot slip the target
    out from under it.
    """
    if pinned_driver_id is None:
        return
    if pinned_driver_id == participant_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="a participant cannot be pinned to themselves",
        )

    found = await session.execute(
        select(Participant.role).where(
            Participant.id == pinned_driver_id,
            Participant.event_id == event.id,
            Participant.status == ParticipantStatus.ACTIVE,
        )
    )
    role = found.scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="pinned_driver_id must name an active participant of this event",
        )
    if role is ParticipantRole.PASSENGER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="pinned_driver_id must name a participant who drives",
        )


async def _written(
    session: AsyncSession, participant: Participant, version: int
) -> ParticipantWritten:
    found = await session.execute(
        select(*_WITH_COORDINATES).where(Participant.id == participant.id)
    )
    return ParticipantWritten(participant=_read(found.one()), participants_version=version)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ParticipantWritten)
async def add_participant(
    payload: ParticipantCreate,
    event: OrganizerEvent,
    session: Session,
    response: Response,
) -> ParticipantWritten:
    """Add someone to the roster.

    A participant token is minted and stored as a digest, but deliberately **not returned**: no
    endpoint accepts one yet, so handing it out would be handing out a credential that does nothing.
    The column is not-null, and a digest nobody holds the preimage of is simply unusable until a
    reissue path exists alongside the participant endpoints (docs/design.md 6.1).
    """
    _require_open_roster(event)

    version = await _bump_version(session, event)
    await _validate_pin(session, event, None, pinned_driver_id=payload.pinned_driver_id)

    participant = Participant(
        event_id=event.id,
        display_name=payload.display_name,
        email=payload.email,
        phone=payload.phone,
        role=payload.role,
        seats_available=payload.seats_available,
        priority=payload.priority,
        pinned_driver_id=payload.pinned_driver_id,
        needs_outbound=payload.needs_outbound,
        needs_return=payload.needs_return,
        pickup_address=payload.pickup.address,
        pickup_geog=point(payload.pickup.lat, payload.pickup.lng),
        #: The caller placed this point by hand, which is the one provenance the design allows to be
        #: stored permanently (docs/design.md 5.2).
        geocode_source=GeocodeSource.USER,
        earliest_departure=payload.earliest_departure,
        latest_arrival=payload.latest_arrival,
        max_detour_minutes=payload.max_detour_minutes,
        notes=payload.notes,
        status=ParticipantStatus.ACTIVE,
        token_hash=hash_token(new_token()),
    )
    session.add(participant)
    await session.flush()

    await _enforce_cap(session, event)

    await session.refresh(participant)
    written = await _written(session, participant, version)
    await session.commit()

    response.headers["Location"] = f"/v1/events/{event.public_id}/participants/{participant.id}"
    return written


@router.get("", response_model=RosterRead)
async def list_participants(event: OrganizerEvent, session: Session) -> RosterRead:
    """The active roster, in the order people were added.

    Cancelled participants are omitted: they are not on the roster, do not count towards the cap and
    are not given to the solver. They remain readable individually, because a solution computed
    before someone dropped out still refers to them.
    """
    found = await session.execute(
        select(*_WITH_COORDINATES)
        .where(
            Participant.event_id == event.id,
            Participant.status == ParticipantStatus.ACTIVE,
        )
        .order_by(Participant.created_at, Participant.id)
    )
    return RosterRead(
        participants_version=event.participants_version,
        participants=[_read(row) for row in found.all()],
    )


@router.get("/{participant_id}", response_model=ParticipantOrganizerRead)
async def get_participant(
    participant_id: uuid.UUID,
    event: OrganizerEvent,
    session: Session,
) -> ParticipantOrganizerRead:
    await _load(session, event, participant_id)
    found = await session.execute(
        select(*_WITH_COORDINATES).where(
            Participant.id == participant_id,
            Participant.event_id == event.id,
        )
    )
    return _read(found.one())


@router.patch("/{participant_id}", response_model=ParticipantWritten)
async def patch_participant(
    participant_id: uuid.UUID,
    payload: ParticipantPatch,
    event: OrganizerEvent,
    session: Session,
) -> ParticipantWritten:
    """Edit on someone's behalf -- the organizer path for "my address changed, can you fix it".

    No cap check: an edit cannot add an active participant, since reactivating a cancelled one is
    deliberately not offered here (re-adding them is a new snapshot, which is the honest record).
    """
    _require_open_roster(event)
    participant = await _load(session, event, participant_id)
    if participant.status is ParticipantStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a cancelled participant cannot be edited; add them again instead",
        )

    changes = payload.changes()
    version = await _bump_version(session, event)

    if "pinned_driver_id" in changes:
        await _validate_pin(
            session, event, participant_id, pinned_driver_id=changes["pinned_driver_id"]
        )

    role = changes.get("role", participant.role)
    seats = changes.get("seats_available", participant.seats_available)
    if seats > 0 and role is ParticipantRole.PASSENGER:
        # Checked against the resulting pair: either field alone can be valid while the combination
        # is not -- the same reason `patch_event` re-checks the event window.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="seats_available must be 0 for a passenger; use role 'driver' or 'either'",
        )
    if not (
        changes.get("needs_outbound", participant.needs_outbound)
        or changes.get("needs_return", participant.needs_return)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="a participant must need at least one leg",
        )

    if (pickup := payload.pickup) is not None:
        participant.pickup_address = pickup.address
        participant.pickup_geog = point(pickup.lat, pickup.lng)
        participant.geocode_source = GeocodeSource.USER
    for field in (
        "display_name",
        "role",
        "seats_available",
        "priority",
        "email",
        "phone",
        "pinned_driver_id",
        "needs_outbound",
        "needs_return",
        "earliest_departure",
        "latest_arrival",
        "max_detour_minutes",
        "notes",
    ):
        if field in changes:
            setattr(participant, field, changes[field])

    await session.flush()
    written = await _written(session, participant, version)
    await session.commit()
    return written


@router.delete("/{participant_id}", response_model=ParticipantWritten)
async def cancel_participant(
    participant_id: uuid.UUID,
    event: OrganizerEvent,
    session: Session,
) -> ParticipantWritten:
    """Take someone off the roster.

    A soft cancel: the row stays, `status` becomes `cancelled`, and the seat is returned to the cap.
    Idempotent -- cancelling an already-cancelled participant still answers 200, because the
    caller's intent is satisfied either way, but it does not bump the version: nothing changed.

    Any pin *pointing at* this person is cleared, or the solver would be left holding a constraint
    naming a driver who is no longer coming.
    """
    _require_open_roster(event)
    participant = await _load(session, event, participant_id)

    if participant.status is ParticipantStatus.CANCELLED:
        return await _written(session, participant, event.participants_version)

    version = await _bump_version(session, event)
    participant.status = ParticipantStatus.CANCELLED
    await session.execute(
        update(Participant)
        .where(
            Participant.event_id == event.id,
            Participant.pinned_driver_id == participant_id,
        )
        .values(pinned_driver_id=None)
        .execution_options(synchronize_session=False)
    )

    await session.flush()
    written = await _written(session, participant, version)
    await session.commit()
    return written
