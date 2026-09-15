"""cascade deletes for event removal

Six foreign keys were created with no delete action, which made `delete from events` fail for any
event that had ever been optimized or had a pin on its roster. `events -> participants` and
`events -> solutions` both cascade, so the cascade deleted participants while routes and stops still
referenced them, and the whole statement aborted.

That matters because "delete this event and everything about it" is the operation the retention and
privacy launch gate requires (docs/design.md 5.3.2), on a table holding home addresses of people who
may be minors. Requiring the caller to delete child tables in the right order is not an acceptable
substitute: a retention job written that way stops being complete the first time a table is added.

The action chosen per key, and why it is not uniform:

* **CASCADE** for the three references into `participants` from the solution side, and for
  `solutions.job_id`. Each child is meaningless without its parent -- a route with no driver, a stop
  with no passenger, a solution with no record of the job that produced it -- and `job_id` is not
  nullable, so SET NULL is not even available. The API never hard-deletes an individual participant
  (cancelling is a status change, docs/design.md 5.3.1), so event deletion is the only path on which
  these fire.
* **SET NULL** for the two pointers that describe a relationship rather than an ownership:
  `participants.pinned_driver_id` and `events.template_event_id`. Losing the driver you were pinned
  to must not delete you, and deleting a template must not delete the events cloned from it.

Nothing here touches data: each statement replaces a constraint with the same constraint plus a
delete action, so the downgrade restores the previous (broken) behaviour exactly.

Revision ID: 391ba919f2d5
Revises: 7cc54778661d
Create Date: 2026-09-15 10:59

"""

from collections.abc import Sequence

from alembic import op

revision: str = "391ba919f2d5"
down_revision: str | Sequence[str] | None = "7cc54778661d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (constraint, child table, parent table, columns, on-delete action).
FOREIGN_KEYS = (
    ("fk_events_template_event_id_events", "events", "events", ["template_event_id"], "SET NULL"),
    (
        "fk_participants_pinned_driver_id_participants",
        "participants",
        "participants",
        ["pinned_driver_id"],
        "SET NULL",
    ),
    (
        "fk_routes_driver_participant_id_participants",
        "routes",
        "participants",
        ["driver_participant_id"],
        "CASCADE",
    ),
    (
        "fk_route_stops_participant_id_participants",
        "route_stops",
        "participants",
        ["participant_id"],
        "CASCADE",
    ),
    (
        "fk_solutions_job_id_optimization_jobs",
        "solutions",
        "optimization_jobs",
        ["job_id"],
        "CASCADE",
    ),
    (
        "fk_unassigned_participants_participant_id_participants",
        "unassigned_participants",
        "participants",
        ["participant_id"],
        "CASCADE",
    ),
)


def _recreate(*, with_actions: bool) -> None:
    """Replace each foreign key, with or without its delete action.

    Postgres has no `ALTER CONSTRAINT` for a delete action, so both directions are a drop and a
    recreate of the same constraint under the same name.
    """
    for name, child, parent, columns, action in FOREIGN_KEYS:
        op.drop_constraint(name, child, type_="foreignkey")
        op.create_foreign_key(
            name, child, parent, columns, ["id"], ondelete=action if with_actions else None
        )


def upgrade() -> None:
    _recreate(with_actions=True)


def downgrade() -> None:
    _recreate(with_actions=False)
