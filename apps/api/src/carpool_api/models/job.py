"""The optimization job queue (docs/design.md 4.2, 5.1).

The queue is Postgres, claimed with `FOR UPDATE SKIP LOCKED`, so job state and domain data commit
in the same transaction and there is no broker to dual-write to.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from carpool_api.models.base import Base, UuidPk, pg_enum
from carpool_api.models.enums import JobStatus

#: The statuses that occupy an event's single job slot and are visible to a claiming worker.
IN_FLIGHT = "status in ('queued', 'running')"


class OptimizationJob(Base):
    __tablename__ = "optimization_jobs"

    id: Mapped[UuidPk]
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    status: Mapped[JobStatus] = mapped_column(pg_enum(JobStatus, "job_status"))
    algorithm: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    #: Hash of the normalized instance, over address *strings* rather than coordinates: geocoders
    #: drift, and fingerprinting resolved points would silently break idempotency
    #: (docs/design.md 5.1, 5.2).
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    #: `events.participants_version` as read at enqueue time. A solution whose input_version is
    #: behind the event's current version is stale.
    input_version: Mapped[int] = mapped_column(BigInteger)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="3")
    worker_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Visibility timeout. A running job whose lease has expired is reclaimable, which is what
    #: makes a worker crash recoverable rather than a stuck job.
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Cancellation is cooperative: the worker checks this between iterations and exits cleanly.
    #: Killing a worker mid-transaction is not safe (docs/design.md 6.3).
    cancel_requested: Mapped[bool] = mapped_column(Boolean, server_default="false")
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        #: At most one in-flight job per event, enforced by the DATABASE rather than app logic.
        #: Two API instances racing to enqueue cannot both succeed: one insert raises a unique
        #: violation, which the API converts to 409 with the existing job id. No distributed lock,
        #: no race window (docs/design.md 5.1).
        Index(
            "one_active_job_per_event",
            "event_id",
            unique=True,
            postgresql_where=text(IN_FLIGHT),
        ),
        #: Supports the SKIP LOCKED claim query, which orders by queued_at.
        Index("jobs_claimable", "queued_at", postgresql_where=text(IN_FLIGHT)),
    )
