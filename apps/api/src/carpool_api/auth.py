"""Resolving the caller's principal (docs/design.md 6.1).

Three principals exist in the design -- organizer, participant, joiner. Week 2 implements the
organizer only: the roster is entered by the coordinator, so the join flow and participant tokens
are not on the critical path (docs/roadmap.md, Week 2). The others get their own dependencies here
when they arrive; they do not get bolted onto this one with a flag.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from carpool_api.db import get_session
from carpool_api.models import Event, EventToken, TokenKind
from carpool_api.security import hash_token

#: `auto_error=False` so that a missing or malformed header lands in the handler below and gets the
#: same 401 as a wrong token. FastAPI's own behaviour is a 403, which is the wrong code and a
#: different body shape for what is the same failure to a client.
_bearer = HTTPBearer(auto_error=False, description="Organizer token, shown once at event creation")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="valid organizer token required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_organizer(
    public_id: Annotated[str, Path(description="The event's public handle")],
    session: Annotated[AsyncSession, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> Event:
    """The event this token administers, or 401.

    An unknown event, a token belonging to a *different* event, a revoked token and an expired one
    all return the same 401. Distinguishing them would make the endpoint an oracle for which event
    handles exist -- and since no unauthenticated read of an event exists in this design, there is
    no case where 404 tells an honest caller something useful.
    """
    if credentials is None:
        raise _unauthorized()

    now = datetime.now(UTC)
    found = await session.execute(
        select(Event)
        .join(EventToken, EventToken.event_id == Event.id)
        .where(
            Event.public_id == public_id,
            EventToken.kind == TokenKind.ORGANIZER,
            EventToken.token_hash == hash_token(credentials.credentials),
            EventToken.revoked_at.is_(None),
            or_(EventToken.expires_at.is_(None), EventToken.expires_at > now),
        )
    )
    event = found.scalar_one_or_none()
    if event is None:
        raise _unauthorized()
    return event


#: Annotated alias so a route reads `event: OrganizerEvent` instead of repeating the Depends.
OrganizerEvent = Annotated[Event, Depends(require_organizer)]
