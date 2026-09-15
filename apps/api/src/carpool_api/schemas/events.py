"""Event payloads (docs/design.md 6).

Coordinates are supplied by the caller. Addresses are the durable record (docs/design.md 5.2), but
the geocoder that resolves one into a point is Week 4 work, so until then the client sends both and
the pair is stored with `geocode_source = 'user'` -- the one provenance the design allows to be kept
permanently. When the geocoder lands, the coordinates become an optional override rather than a
requirement, and nothing about the stored shape changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self
from zoneinfo import ZoneInfo, available_timezones

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from carpool_api.models import Event, EventStatus

NAME_MAX = 200
ADDRESS_MAX = 500


def _known_timezone(value: str) -> str:
    """An IANA zone name the *server* can resolve.

    The event stores a zone name because a coordinator reasons in wall-clock time ("practice at
    4pm"), and a stored UTC instant alone cannot survive a daylight-saving boundary being moved.
    A name this machine cannot load would make every derived local time a runtime error later, so it
    is rejected at the edge.
    """
    try:
        ZoneInfo(value)
    except (KeyError, ValueError):
        raise ValueError(f"unknown IANA time zone: {value!r}") from None
    if value not in available_timezones():
        raise ValueError(f"unknown IANA time zone: {value!r}")
    return value


class Destination(BaseModel):
    """Where the event is. Latitude first, as in every payload this API accepts."""

    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=1, max_length=ADDRESS_MAX)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class EventCreate(BaseModel):
    """`extra="forbid"` throughout: a misspelled field is a bug, and silently ignoring it is worse
    than a 422 -- an event created with a mistyped `ends_at` looks like it worked."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=NAME_MAX)
    destination: Destination
    #: Everyone must be at the destination by this time; pickups are scheduled backward from it.
    arrival_at: AwareDatetime
    #: When the event ends and the return leg departs; drop-offs schedule forward from it.
    ends_at: AwareDatetime
    timezone: str

    _check_timezone = field_validator("timezone")(_known_timezone)

    @model_validator(mode="after")
    def _ends_after_arrival(self) -> Self:
        """Mirrors both the `ck_events_ends_after_arrival` constraint and `ProblemInstance`'s own
        rule, so the caller gets a 422 naming the field rather than a 500 from the database."""
        if self.ends_at <= self.arrival_at:
            raise ValueError("ends_at must be after arrival_at")
        return self


class EventPatch(BaseModel):
    """Every field optional; only those actually sent are applied (`exclude_unset`).

    The destination moves as a unit -- an address without its coordinates would leave the two
    describing different places, and there is no geocoder yet to re-derive one from the other.
    That is why `destination` is a nested object here rather than three sibling fields.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    destination: Destination | None = None
    arrival_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    timezone: str | None = None

    _check_timezone = field_validator("timezone")(_known_timezone)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("no fields to update")
        return self

    def changes(self) -> dict[str, Any]:
        """The fields the caller actually sent, `destination` included as the nested object."""
        return self.model_dump(exclude_unset=True)


class EventOrganizerRead(BaseModel):
    """The organizer's view of an event.

    The participant and joiner views are separate classes, added with the join flow. This one is
    unredacted; being explicit about that is the point of having one model per audience.
    """

    public_id: str
    name: str
    destination: Destination
    arrival_at: datetime
    ends_at: datetime
    timezone: str
    status: EventStatus
    #: Bumped by every roster change. An organizer client holds it to detect that a solution it is
    #: looking at has gone stale (docs/design.md 5.1).
    participants_version: int
    created_at: datetime

    @classmethod
    def of(cls, event: Event, lat: float, lng: float) -> Self:
        """Built field by field rather than from ORM attributes, so adding a column to the table
        cannot quietly add it to a response."""
        return cls(
            public_id=event.public_id,
            name=event.name,
            destination=Destination(address=event.destination_address, lat=lat, lng=lng),
            arrival_at=event.arrival_at,
            ends_at=event.ends_at,
            timezone=event.timezone,
            status=event.status,
            participants_version=event.participants_version,
            created_at=event.created_at,
        )


class EventCreated(BaseModel):
    """The one and only time the organizer token is visible.

    Only its SHA-256 digest is stored, so a lost token cannot be recovered -- it can only be
    reissued. There is deliberately no `join_url` yet: minting a join token while no endpoint
    accepts one would hand the caller a link that silently does nothing (docs/roadmap.md, Week 2).
    """

    event: EventOrganizerRead
    organizer_token: str
    organizer_token_expires_at: datetime
