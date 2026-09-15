"""Participants -- the roster (docs/design.md 5, 5.2, 5.3).

This table holds people's home addresses, so it is the privacy-sensitive centre of the schema
(CLAUDE.md, docs/design.md 5.3.2). Fixtures for it are generated, never dumped from a real event.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from carpool_api.models.base import Base, TimestampTz, UuidPk, pg_enum
from carpool_api.models.enums import (
    GeocodeSource,
    ParticipantRole,
    ParticipantStatus,
    PrecisionLevel,
)


class Participant(Base):
    """One person's participation in one event.

    This is an immutable *snapshot*, not a person record: it says where someone was picked up for
    this event, and stays truthful after they move (docs/design.md 5.3.1). A canonical address book
    is deferred until accounts exist.
    """

    __tablename__ = "participants"

    id: Mapped[UuidPk]
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    display_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[ParticipantRole] = mapped_column(pg_enum(ParticipantRole, "participant_role"))
    seats_available: Mapped[int] = mapped_column(Integer, server_default="0")
    #: Generic priority; scales the unassigned penalty. Deliberately not a seniority model --
    #: priority stays out of the optimizer's structure (docs/design.md 2.2).
    priority: Mapped[int] = mapped_column(Integer, server_default="0")
    #: Organizer override: force this person into a particular car.
    pinned_driver_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("participants.id"), nullable=True
    )
    needs_outbound: Mapped[bool] = mapped_column(Boolean, server_default="true")
    needs_return: Mapped[bool] = mapped_column(Boolean, server_default="true")
    #: The durable record. Coordinates are derived and cached with a TTL (docs/design.md 5.2).
    pickup_address: Mapped[str] = mapped_column(Text)
    #: Nullable on purpose: persisted only when a human placed it, never when a provider returned
    #: it. See `geocode_source` and docs/design.md 5.2.
    pickup_geog: Mapped[object | None] = mapped_column(
        Geography("POINT", srid=4326, spatial_index=False), nullable=True
    )
    geocode_source: Mapped[GeocodeSource] = mapped_column(
        pg_enum(GeocodeSource, "geocode_source"), server_default=GeocodeSource.PROVIDER.value
    )
    pickup_precision: Mapped[PrecisionLevel] = mapped_column(
        pg_enum(PrecisionLevel, "precision_level"), server_default=PrecisionLevel.EXACT.value
    )
    earliest_departure: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latest_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_detour_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ParticipantStatus] = mapped_column(
        pg_enum(ParticipantStatus, "participant_status"),
        server_default=ParticipantStatus.ACTIVE.value,
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    #: `onupdate` is SQLAlchemy-side, emitted with every UPDATE this mapper issues -- it is not DDL,
    #: so it needs no migration and autogenerate does not see it. A database trigger would also
    #: cover hand-written SQL, which is not worth a trigger here: every write goes through the API.
    updated_at: Mapped[TimestampTz] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("seats_available >= 0", name="seats_available_non_negative"),
        #: GiST, not btree -- a btree index on a geography column cannot answer distance queries.
        Index("ix_participants_pickup_geog", "pickup_geog", postgresql_using="gist"),
        #: Partial: the cap and every roster read count active participants only, so cancelled
        #: rows do not need to sit in the index (docs/design.md 5.1).
        Index(
            "ix_participants_event_id_active",
            "event_id",
            postgresql_where=text("status = 'active'"),
        ),
    )
