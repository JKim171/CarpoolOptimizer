"""Solutions, routes, and stops -- the solver's output, persisted (docs/design.md 5, 8.2).

A car keeps the same riders both ways, so one `Route` covers both legs; only the stop order and the
geometry are per leg, because the two legs are sequenced independently against an asymmetric matrix.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from carpool_api.models.base import Base, TimestampTz, UuidPk, pg_enum
from carpool_api.models.enums import RouteLeg


class Solution(Base):
    __tablename__ = "solutions"

    id: Mapped[UuidPk]
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    #: Cascades for the same reason as `event_id`: deleting an event deletes its jobs, and a
    #: solution whose job is gone has lost the record of how it was produced. Not nullable, so
    #: SET NULL is not an option.
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("optimization_jobs.id", ondelete="CASCADE")
    )
    algorithm: Mapped[str] = mapped_column(Text)
    objective_value: Mapped[float] = mapped_column(Float)
    #: drive_s, vehicles, p95_detour_s, churn, gap_to_bound.
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    #: Stale when below the event's current `participants_version` (docs/design.md 5.1).
    input_version: Mapped[int] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    routes: Mapped[list[Route]] = relationship(
        back_populates="solution", cascade="all, delete-orphan"
    )
    #: A relationship rather than rows inserted separately, so a solution and the reasons somebody
    #: went without a ride commit as one graph. Relationships are mapper-level, not DDL -- this adds
    #: no migration.
    unassigned: Mapped[list[UnassignedParticipant]] = relationship(
        back_populates="solution", cascade="all, delete-orphan"
    )

    __table_args__ = (
        #: One active solution per event, enforced by the database for the same reason as
        #: one_active_job_per_event: activation races cannot produce two live answers.
        Index(
            "one_active_solution_per_event",
            "event_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )


class Route(Base):
    """One car, both legs."""

    __tablename__ = "routes"

    id: Mapped[UuidPk]
    solution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("solutions.id", ondelete="CASCADE"))
    #: Cascades so that deleting an event can succeed: the event's participants go with it, and a
    #: route without its driver is not a route. The API never hard-deletes an individual participant
    #: -- cancelling is a status change (docs/design.md 5.3.1) -- so event deletion is the only path
    #: this fires on.
    driver_participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE")
    )
    seats_used: Mapped[int] = mapped_column(Integer)
    #: Both legs combined. Integer seconds and metres throughout (CLAUDE.md).
    total_distance_m: Mapped[int] = mapped_column(Integer)
    total_duration_s: Mapped[int] = mapped_column(Integer)
    #: Versus this driver's direct round trip, both legs.
    detour_seconds: Mapped[int] = mapped_column(Integer)
    #: Null until first viewed. Geometry is fetched lazily because the directions quota binds long
    #: before the matrix quota does (docs/design.md 4.4).
    outbound_geometry: Mapped[object | None] = mapped_column(
        Geometry("LINESTRING", srid=4326, spatial_index=False), nullable=True
    )
    return_geometry: Mapped[object | None] = mapped_column(
        Geometry("LINESTRING", srid=4326, spatial_index=False), nullable=True
    )

    solution: Mapped[Solution] = relationship(back_populates="routes")
    stops: Mapped[list[RouteStop]] = relationship(
        back_populates="route", cascade="all, delete-orphan"
    )


class RouteStop(Base):
    """A position in one leg's ordering.

    Routes store orderings, not schedules -- but `eta` is persisted so the results screen and the
    participant view do not each re-derive it. It is recomputed whenever the matrix is refreshed
    (CLAUDE.md).
    """

    __tablename__ = "route_stops"

    id: Mapped[UuidPk]
    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"))
    #: The two legs carry different orders on purpose -- the travel matrix is asymmetric
    #: (docs/design.md 8.2).
    leg: Mapped[RouteLeg] = mapped_column(pg_enum(RouteLeg, "route_leg"))
    seq: Mapped[int] = mapped_column(Integer)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE")
    )
    #: Pickup time outbound, drop-off time on return.
    eta: Mapped[TimestampTz]

    route: Mapped[Route] = relationship(back_populates="stops")

    __table_args__ = (UniqueConstraint("route_id", "leg", "seq", name="uq_route_stops_ordering"),)


class UnassignedParticipant(Base):
    """Why someone did not get a ride. Surfacing the reason is a product requirement, not a log."""

    __tablename__ = "unassigned_participants"

    solution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("solutions.id", ondelete="CASCADE"), primary_key=True
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), primary_key=True
    )
    #: no_capacity | detour_exceeded | time_window | no_drivers
    reason: Mapped[str] = mapped_column(Text)

    solution: Mapped[Solution] = relationship(back_populates="unassigned")
