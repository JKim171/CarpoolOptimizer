"""Postgres enum types (docs/design.md 5).

These are database enums rather than check constraints so an invalid value cannot be written by any
client, including psql. Adding a value later is `ALTER TYPE ... ADD VALUE` in a migration; removing
one is not supported by Postgres, so add deliberately.

`ParticipantRole` mirrors `carpool_domain.Role` but is declared separately: the domain must not be
importable from a database column definition (docs/design.md 4.1). `test_schema.py` asserts the two
stay in step.
"""

from __future__ import annotations

import enum


class EventStatus(enum.StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    LOCKED = "locked"
    ARCHIVED = "archived"


class TokenKind(enum.StrEnum):
    ORGANIZER = "organizer"
    JOIN = "join"


class ParticipantRole(enum.StrEnum):
    DRIVER = "driver"
    PASSENGER = "passenger"
    #: Dormant by decision, not dead code -- the MVP roster UI does not offer it (CLAUDE.md,
    #: docs/design.md 2.3). The column must still accept it.
    EITHER = "either"


class ParticipantStatus(enum.StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class GeocodeSource(enum.StrEnum):
    #: Resolved by the geocoding provider; cached with a TTL, never a permanent store.
    PROVIDER = "provider"
    #: Placed by a human dragging a pin, so it is not provider output and may be kept permanently
    #: (docs/design.md 5.2).
    USER = "user"


class PrecisionLevel(enum.StrEnum):
    EXACT = "exact"
    STREET = "street"
    NEIGHBORHOOD = "neighborhood"


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RouteLeg(enum.StrEnum):
    OUTBOUND = "outbound"
    RETURN = "return"
