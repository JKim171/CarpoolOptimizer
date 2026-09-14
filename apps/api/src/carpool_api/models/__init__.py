"""SQLAlchemy models -- the single source of truth for the schema (docs/design.md 5).

Alembic autogenerates against `Base.metadata`, so every model module must be imported here or its
tables are invisible to migrations and the drift test.
"""

from carpool_api.models.base import Base
from carpool_api.models.cache import GeocodeCache, TravelCache
from carpool_api.models.enums import (
    EventStatus,
    GeocodeSource,
    JobStatus,
    ParticipantRole,
    ParticipantStatus,
    PrecisionLevel,
    RouteLeg,
    TokenKind,
)
from carpool_api.models.event import Event, EventToken
from carpool_api.models.job import OptimizationJob
from carpool_api.models.participant import Participant
from carpool_api.models.solution import Route, RouteStop, Solution, UnassignedParticipant

__all__ = [
    "Base",
    "Event",
    "EventStatus",
    "EventToken",
    "GeocodeCache",
    "GeocodeSource",
    "JobStatus",
    "OptimizationJob",
    "Participant",
    "ParticipantRole",
    "ParticipantStatus",
    "PrecisionLevel",
    "Route",
    "RouteLeg",
    "RouteStop",
    "Solution",
    "TokenKind",
    "TravelCache",
    "UnassignedParticipant",
]
