"""Optimization job payloads (docs/design.md 6, 4.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict

from carpool_api.models import JobStatus, OptimizationJob
from carpool_api.schemas.weights import Weights

#: The only algorithm a user request may ask for.
#:
#: CP-SAT is deliberately absent: it is a measuring instrument, not a product feature. It costs
#: ~400 MB per solve on a 2 GB host, its runtime varies wildly, and the 50-participant cap sits past
#: the ~40 where it reliably proves optimality -- so it runs in the benchmark harness and never on a
#: user request, which is also what keeps OR-Tools out of the production image (docs/design.md 8.3).
#: LNS joins this list in Week 4.
Algorithm = Literal["greedy"]


class OptimizationCreate(BaseModel):
    """What to solve and how.

    No `preserve_previous` yet, though docs/design.md 6 lists one: it would set the churn weight
    against the previously activated solution, and greedy cannot steer by churn: it constructs
    from nothing. The flag arrives with LNS, whose acceptance criterion can actually honour it
    (docs/design.md 8.4). Offering it now would be a switch that silently does nothing.
    """

    model_config = ConfigDict(extra="forbid")

    algorithm: Algorithm = "greedy"
    #: Overrides `events.settings` for this job only. The effective set is recorded in
    #: `optimization_jobs.params`, so the job stays reproducible after the event's settings change.
    weights: Weights | None = None


class JobRead(BaseModel):
    """A job as the client polls it (docs/design.md 4.3 -- polling, not SSE, in v1)."""

    job_id: uuid.UUID
    event_public_id: str
    status: JobStatus
    algorithm: str
    #: The weights this job actually ran with, resolved from request and event settings.
    weights: Weights
    #: `events.participants_version` as read at enqueue time. A solution whose version is behind the
    #: event's current one describes a roster that has since changed (docs/design.md 5.1).
    input_version: int
    progress: dict[str, Any] | None
    error: str | None
    #: Present once the job has succeeded.
    solution_id: uuid.UUID | None
    cancel_requested: bool
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def of(
        cls, job: OptimizationJob, *, event_public_id: str, solution_id: uuid.UUID | None
    ) -> Self:
        return cls(
            job_id=job.id,
            event_public_id=event_public_id,
            status=job.status,
            algorithm=job.algorithm,
            weights=Weights.model_validate(job.params.get("weights") or {}),
            input_version=job.input_version,
            progress=job.progress,
            error=job.error,
            solution_id=solution_id,
            cancel_requested=job.cancel_requested,
            queued_at=job.queued_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class JobConflict(BaseModel):
    """The 409 body when a job is already in flight for this event.

    Carries the existing job id so the client polls that one instead of retrying -- a retry would
    hit the same partial unique index and fail again (docs/design.md 5.1).
    """

    detail: str
    #: Null in the narrow case where the job that won the race finished between the failed insert
    #: and the lookup. The conflict was still real; there is simply nothing left to poll, and the
    #: client should just try again.
    existing_job_id: uuid.UUID | None
