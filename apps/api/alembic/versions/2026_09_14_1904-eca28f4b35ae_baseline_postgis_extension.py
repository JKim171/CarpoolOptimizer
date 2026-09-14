"""baseline: postgis extension

The Postgres image makes the PostGIS package available but does not create the extension
(docker/postgres/Dockerfile, docs/design.md 10.1), so every database gets it from this migration --
development, production, and testcontainers alike.

`if not exists` is load-bearing: the developer's existing `carpool` volume already has the
extension from a smoke test run by hand, and this migration must be a no-op there rather than an
error.

Dropping PostGIS on downgrade would take any `geography` column with it. Since the tables that use
those columns are created by later migrations, downgrading past this point means the schema is
already gone, and the extension is left in place deliberately.

Revision ID: eca28f4b35ae
Revises:
Create Date: 2026-09-14 19:04

"""

from collections.abc import Sequence

from alembic import op

revision: str = "eca28f4b35ae"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("create extension if not exists postgis")


def downgrade() -> None:
    """Deliberately empty -- see the module docstring."""
