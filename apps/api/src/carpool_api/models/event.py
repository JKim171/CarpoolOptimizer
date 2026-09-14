"""Events and the tokens that grant access to them (docs/design.md 5, 6.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from carpool_api.models.base import Base, TimestampTz, UuidPk, pg_enum
from carpool_api.models.enums import EventStatus, TokenKind


class Event(Base):
    __tablename__ = "events"

    id: Mapped[UuidPk]
    #: Short slug used in share URLs; the public handle for the event.
    public_id: Mapped[str] = mapped_column(Text, unique=True)
    #: Null until accounts exist (docs/design.md 6.1). Deliberately carries no foreign key: there
    #: is no `users` table yet, and adding one later is an ALTER, not a rewrite.
    organizer_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    organizer_email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    name: Mapped[str] = mapped_column(Text)
    destination_address: Mapped[str] = mapped_column(Text)
    destination_geog: Mapped[Any] = mapped_column(
        Geography("POINT", srid=4326, spatial_index=False)
    )
    arrival_at: Mapped[TimestampTz]
    #: When the return leg departs; drop-off ETAs count forward from it.
    ends_at: Mapped[TimestampTz]
    #: IANA zone name. Stored because a wall-clock time is what the organizer reasons about.
    timezone: Mapped[str] = mapped_column(Text)
    status: Mapped[EventStatus] = mapped_column(pg_enum(EventStatus, "event_status"))
    #: Objective weights and detour caps; shaped by the domain's ObjectiveWeights.
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    #: Clone lineage for roster reuse (docs/design.md 5.3.1).
    template_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id"), nullable=True
    )
    #: Bumped on every participant insert/update/delete. Taking this row's lock is what makes both
    #: the 50-participant cap and stale-solution detection race-free (docs/design.md 5.1).
    participants_version: Mapped[int] = mapped_column(BigInteger, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tokens: Mapped[list[EventToken]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (
        #: Mirrors the domain's own requirement that an event end after it starts (CLAUDE.md).
        CheckConstraint("ends_at > arrival_at", name="ends_after_arrival"),
    )


class EventToken(Base):
    """Organizer and join tokens. Only the SHA-256 hash is stored; plaintext is shown once."""

    __tablename__ = "event_tokens"

    id: Mapped[UuidPk]
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
    )
    kind: Mapped[TokenKind] = mapped_column(pg_enum(TokenKind, "token_kind"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped[Event] = relationship(back_populates="tokens")
