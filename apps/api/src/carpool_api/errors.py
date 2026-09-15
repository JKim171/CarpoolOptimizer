"""Turning database constraint violations into HTTP answers.

Several of this design's invariants are enforced by the database rather than by application logic --
the single in-flight job per event, the single active solution, the unique public handle
(docs/design.md 5.1). That is deliberate: two API processes racing cannot both win. The cost is that
the API learns about the loss as an `IntegrityError`, and has to tell one constraint from another.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError


def violates(exc: IntegrityError, constraint: str) -> bool:
    """True when `exc` reports a violation of the named constraint.

    Matched against the message text because SQLAlchemy's asyncpg wrapper does not forward
    asyncpg's structured `constraint_name`. Postgres always names the constraint in the message, and
    the schema's naming convention makes those names explicit and stable rather than
    server-invented (`models/base.py`).
    """
    return constraint in str(exc.orig)
