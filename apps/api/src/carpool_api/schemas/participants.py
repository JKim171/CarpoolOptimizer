"""Roster payloads (docs/design.md 6, 5.3).

A participant row is a **snapshot of one person's participation in one event**, not a person record
(docs/design.md 5.3.1): it records where someone was picked up for this event and stays truthful
after they move. That is why these payloads carry an address rather than a reference to an address
book, and why cancelling is a status change rather than a delete.

This is also the privacy-sensitive centre of the schema -- it holds home addresses, for groups that
may include minors (CLAUDE.md). The organizer view below is unredacted by design; the participant
view, which is not, arrives with the join flow as its own class.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from carpool_api.models import Participant, ParticipantRole, ParticipantStatus

NAME_MAX = 120
ADDRESS_MAX = 500
CONTACT_MAX = 200
NOTES_MAX = 1000

#: Passengers one car can carry. A generous upper bound on a sedan or minivan, present to stop a
#: typo ("70" for "7") from silently creating a bus.
SEATS_MAX = 8

#: A rider's own tolerance, in minutes, because that is the unit an organizer types. The domain
#: works in seconds and the adapter converts (CLAUDE.md).
MAX_DETOUR_MINUTES_MAX = 240


def _clean_contact(value: str | None) -> str | None:
    """Trim, and reject what is obviously not a contact detail.

    Deliberately not a full email grammar: nothing sends mail yet, and a strict regex rejects valid
    addresses. Real validation belongs where a message is actually dispatched, which is where a
    wrong address produces a visible failure instead of a silent one.
    """
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if any(character.isspace() for character in cleaned):
        raise ValueError("must not contain whitespace")
    return cleaned


def _clean_email(value: str | None) -> str | None:
    cleaned = _clean_contact(value)
    if cleaned is None:
        return None
    local, _, domain = cleaned.partition("@")
    if not local or not domain or "@" in domain:
        raise ValueError("must be an email address")
    return cleaned


class Pickup(BaseModel):
    """Where this person is collected. Latitude first, as everywhere in this API.

    Coordinates are required until the Week 4 geocoder can derive them from the address, at which
    point they become an optional override. They are stored on the participant row with
    `geocode_source = 'user'` -- provider-resolved coordinates go to the TTL'd cache instead, which
    is what keeps the choice of geocoder reversible (docs/design.md 5.2).
    """

    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=1, max_length=ADDRESS_MAX)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class PickupRead(BaseModel):
    """Coordinates are nullable on the way out: from Week 4 a provider-geocoded participant has none
    of their own, and the solve-time cache supplies them."""

    address: str
    lat: float | None
    lng: float | None


class _ParticipantFields(BaseModel):
    """Shared validation, so create and patch cannot drift apart."""

    model_config = ConfigDict(extra="forbid")

    # `check_fields=False` because the fields themselves are declared by the subclasses; this base
    # exists so create and patch cannot validate contact details differently.
    _clean_email_field = field_validator("email", check_fields=False)(_clean_email)
    _clean_phone_field = field_validator("phone", check_fields=False)(_clean_contact)


class ParticipantCreate(_ParticipantFields):
    display_name: str = Field(min_length=1, max_length=NAME_MAX)
    pickup: Pickup
    #: `either` -- has a car but will ride instead -- is accepted here even though the MVP roster UI
    #: does not offer it. It is dormant by decision, not dead code (CLAUDE.md, docs/design.md 2.3).
    role: ParticipantRole = ParticipantRole.PASSENGER
    #: Passengers this person can carry, excluding themselves.
    seats_available: int = Field(default=0, ge=0, le=SEATS_MAX)
    #: Scarcity weight scaling the unassigned penalty -- not a seniority model
    #: (docs/design.md 2.2).
    priority: int = Field(default=0, ge=0, le=100)
    email: str | None = Field(default=None, max_length=CONTACT_MAX)
    phone: str | None = Field(default=None, max_length=CONTACT_MAX)
    pinned_driver_id: uuid.UUID | None = None
    needs_outbound: bool = True
    needs_return: bool = True
    earliest_departure: AwareDatetime | None = None
    latest_arrival: AwareDatetime | None = None
    max_detour_minutes: int | None = Field(default=None, ge=0, le=MAX_DETOUR_MINUTES_MAX)
    notes: str | None = Field(default=None, max_length=NOTES_MAX)

    @model_validator(mode="after")
    def _seats_belong_to_someone_who_drives(self) -> Self:
        """A passenger with seats is a data-entry mistake worth surfacing.

        Someone who has a car but would rather ride is exactly what the `either` role is for, so
        there is a correct way to express this and silently ignoring the seats would hide it.
        """
        if self.seats_available > 0 and self.role is ParticipantRole.PASSENGER:
            raise ValueError(
                "seats_available must be 0 for a passenger; use role 'driver' or 'either'"
            )
        return self

    @model_validator(mode="after")
    def _needs_at_least_one_leg(self) -> Self:
        if not (self.needs_outbound or self.needs_return):
            raise ValueError("a participant must need at least one leg")
        return self


class ParticipantPatch(_ParticipantFields):
    """Every field optional. The pickup moves as a unit, as the event's destination does."""

    display_name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    pickup: Pickup | None = None
    role: ParticipantRole | None = None
    seats_available: int | None = Field(default=None, ge=0, le=SEATS_MAX)
    priority: int | None = Field(default=None, ge=0, le=100)
    email: str | None = Field(default=None, max_length=CONTACT_MAX)
    phone: str | None = Field(default=None, max_length=CONTACT_MAX)
    pinned_driver_id: uuid.UUID | None = None
    needs_outbound: bool | None = None
    needs_return: bool | None = None
    earliest_departure: AwareDatetime | None = None
    latest_arrival: AwareDatetime | None = None
    max_detour_minutes: int | None = Field(default=None, ge=0, le=MAX_DETOUR_MINUTES_MAX)
    notes: str | None = Field(default=None, max_length=NOTES_MAX)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("no fields to update")
        return self

    def changes(self) -> dict[str, Any]:
        """Only the fields the caller actually sent.

        `exclude_unset` rather than `exclude_none`: clearing an optional field by sending `null` --
        removing a pin, dropping a phone number -- has to be distinguishable from not mentioning it.
        """
        return self.model_dump(exclude_unset=True)


class ParticipantOrganizerRead(BaseModel):
    """The organizer's view: everything, contact details and full address included.

    Built field by field so that adding a column to `participants` cannot quietly add it to a
    response -- which on this table would mean leaking `token_hash` or a pickup point.
    """

    id: uuid.UUID
    display_name: str
    pickup: PickupRead
    role: ParticipantRole
    seats_available: int
    priority: int
    email: str | None
    phone: str | None
    pinned_driver_id: uuid.UUID | None
    needs_outbound: bool
    needs_return: bool
    earliest_departure: datetime | None
    latest_arrival: datetime | None
    max_detour_minutes: int | None
    notes: str | None
    status: ParticipantStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, participant: Participant, lat: float | None, lng: float | None) -> Self:
        return cls(
            id=participant.id,
            display_name=participant.display_name,
            pickup=PickupRead(address=participant.pickup_address, lat=lat, lng=lng),
            role=participant.role,
            seats_available=participant.seats_available,
            priority=participant.priority,
            email=participant.email,
            phone=participant.phone,
            pinned_driver_id=participant.pinned_driver_id,
            needs_outbound=participant.needs_outbound,
            needs_return=participant.needs_return,
            earliest_departure=participant.earliest_departure,
            latest_arrival=participant.latest_arrival,
            max_detour_minutes=participant.max_detour_minutes,
            notes=participant.notes,
            status=participant.status,
            created_at=participant.created_at,
            updated_at=participant.updated_at,
        )


class RosterRead(BaseModel):
    """The active roster, with the version it was read at.

    The version travels with the roster so a client can tell that a solution it is displaying was
    computed against an earlier one (docs/design.md 5.1).
    """

    participants_version: int
    participants: list[ParticipantOrganizerRead]


class ParticipantWritten(BaseModel):
    """The result of any single roster mutation, with the version that mutation produced."""

    participant: ParticipantOrganizerRead
    participants_version: int
