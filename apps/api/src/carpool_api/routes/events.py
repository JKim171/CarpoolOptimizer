"""Event endpoints (docs/design.md 6).

Organizer principal only, which is what Model A -- the coordinator types in the whole roster --
allows (docs/design.md 2.1, docs/roadmap.md Week 2). `POST /v1/events` is therefore the only
unauthenticated endpoint in the group: it is what mints the credential the others require.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from carpool_api.auth import OrganizerEvent
from carpool_api.db import get_session
from carpool_api.errors import violates
from carpool_api.geo import latitude_of, longitude_of, point
from carpool_api.models import Event, EventStatus, EventToken, TokenKind
from carpool_api.schemas.events import (
    Destination,
    EventCreate,
    EventCreated,
    EventOrganizerRead,
    EventPatch,
)
from carpool_api.security import hash_token, new_public_id, new_token

router = APIRouter(prefix="/v1/events", tags=["events"])

Session = Annotated[AsyncSession, Depends(get_session)]

#: Long enough to outlive any event being planned today, short enough that a link forwarded into a
#: mailing list does not stay live indefinitely. Renewal arrives with accounts, which is when an
#: organizer has an identity that can be re-authenticated (docs/design.md 6.1).
ORGANIZER_TOKEN_TTL = timedelta(days=90)

#: A 10-character handle out of a 31-character alphabet is ~50 bits; a collision is not a practical
#: event. Retried rather than left to 500, because the failure is both harmless and recoverable.
PUBLIC_ID_ATTEMPTS = 5

_UNIQUE_PUBLIC_ID = "uq_events_public_id"


async def _destination_of(session: AsyncSession, event: Event) -> Destination:
    """Read the stored point back as latitude/longitude.

    A second query on the primary key rather than decoding the geography blob in Python: PostGIS is
    the thing that understands the type, and this keeps a geometry library out of the image
    (`geo.py`).
    """
    found = await session.execute(
        select(
            latitude_of(Event.destination_geog),
            longitude_of(Event.destination_geog),
        ).where(Event.id == event.id)
    )
    lat, lng = found.one()
    return Destination(address=event.destination_address, lat=lat, lng=lng)


async def _read(session: AsyncSession, event: Event) -> EventOrganizerRead:
    destination = await _destination_of(session, event)
    return EventOrganizerRead.of(event, destination.lat, destination.lng)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=EventCreated)
async def create_event(
    payload: EventCreate,
    response: Response,
    session: Session,
) -> EventCreated:
    """Create an event and mint its organizer token.

    Status is `open` on creation: in Model A there is no submission window to wait for, so a `draft`
    state would be a step every organizer immediately skips.
    """
    token = new_token()
    expires_at = datetime.now(UTC) + ORGANIZER_TOKEN_TTL

    event: Event | None = None
    for _ in range(PUBLIC_ID_ATTEMPTS):
        candidate = Event(
            public_id=new_public_id(),
            name=payload.name,
            destination_address=payload.destination.address,
            destination_geog=point(payload.destination.lat, payload.destination.lng),
            arrival_at=payload.arrival_at,
            ends_at=payload.ends_at,
            timezone=payload.timezone,
            status=EventStatus.OPEN,
            tokens=[
                EventToken(
                    kind=TokenKind.ORGANIZER,
                    token_hash=hash_token(token),
                    expires_at=expires_at,
                )
            ],
        )
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
        except IntegrityError as exc:
            if not violates(exc, _UNIQUE_PUBLIC_ID):
                raise
            continue  # the savepoint rollback has already detached `candidate`
        event = candidate
        break

    if event is None:  # pragma: no cover -- five collisions in a row is not a reachable state
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not allocate a unique event id",
        )

    # `created_at` and `participants_version` come from server defaults, so they are unset on the
    # in-memory object until it is read back.
    await session.refresh(event)
    read = await _read(session, event)
    await session.commit()

    response.headers["Location"] = f"{router.prefix}/{event.public_id}"
    return EventCreated(
        event=read,
        organizer_token=token,
        organizer_token_expires_at=expires_at,
    )


@router.get("/{public_id}", response_model=EventOrganizerRead)
async def get_event(event: OrganizerEvent, session: Session) -> EventOrganizerRead:
    return await _read(session, event)


@router.patch("/{public_id}", response_model=EventOrganizerRead)
async def patch_event(
    payload: EventPatch,
    event: OrganizerEvent,
    session: Session,
) -> EventOrganizerRead:
    """Edit event details.

    Permitted while the event is locked: locking freezes the *roster*, and a venue or time change is
    exactly the kind of correction an organizer needs to make after that point. An archived event is
    immutable.
    """
    if event.status is EventStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an archived event cannot be edited",
        )

    changes = payload.changes()

    arrival_at = changes.get("arrival_at", event.arrival_at)
    ends_at = changes.get("ends_at", event.ends_at)
    if ends_at <= arrival_at:
        # Checked against the *resulting* pair, which a single-field patch can invalidate without
        # either value on its own being wrong.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ends_at must be after arrival_at",
        )

    if (destination := payload.destination) is not None:
        event.destination_address = destination.address
        event.destination_geog = point(destination.lat, destination.lng)
    for field in ("name", "arrival_at", "ends_at", "timezone"):
        if field in changes:
            setattr(event, field, changes[field])

    await session.flush()
    read = await _read(session, event)
    await session.commit()
    return read


@router.post("/{public_id}/lock", response_model=EventOrganizerRead)
async def lock_event(event: OrganizerEvent, session: Session) -> EventOrganizerRead:
    """Freeze the roster. Idempotent -- re-locking a locked event is a no-op, not an error, because
    a double-tapped button is not a conflict."""
    if event.status is EventStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an archived event cannot be locked",
        )

    if event.status is not EventStatus.LOCKED:
        event.status = EventStatus.LOCKED
        await session.flush()

    read = await _read(session, event)
    await session.commit()
    return read
