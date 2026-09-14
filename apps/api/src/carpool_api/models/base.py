"""Declarative base and shared column types.

These models are the single source of truth for the schema: Alembic autogenerates against
`Base.metadata`, and `test_schema.py` fails the build if the two ever drift (docs/design.md 5).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, Enum, MetaData
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, mapped_column

#: Naming convention so autogenerate emits stable, explicit constraint names. Without it Postgres
#: invents them, a later migration cannot reliably drop a constraint by name, and the drift test
#: reports differences that are only naming noise.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: Every timestamp column is timezone-aware. The domain works in epoch seconds (CLAUDE.md); the
#: conversion happens in the adapter that builds a ProblemInstance, never in the database.
TimestampTz = Annotated[datetime, mapped_column(DateTime(timezone=True))]

UuidPk = Annotated[
    uuid.UUID,
    mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
]


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """A Postgres enum storing member *values* ("driver"), not Python attribute names ("DRIVER").

    Without `values_callable` SQLAlchemy stores the attribute name, which would put SHOUTING
    strings in the database and break every hand-written query in docs/design.md.
    """
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
