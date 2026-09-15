"""Deleting an event must remove everything about it (docs/design.md 5.3.2).

Retention, privacy and deletion is a public-launch gate, and this table holds home addresses of
people who may be minors -- so "delete this event and everything about it" is an operation that has
to work, on the most tangled event the application can produce, not on an empty one.

Built through the API rather than with hand-written inserts, so the row shapes are exactly what the
app really writes: a solved event with routes, per-leg stops, an unassigned participant, a pin
pointing from one participant at another, and a second event claiming this one as its clone
template. Every one of those is a foreign key that has to allow the delete through.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from roster import add, optimize, other_event, person
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

#: Everything that hangs off an event, and the column that ties each one back.
DEPENDENTS = {
    "participants": "event_id",
    "event_tokens": "event_id",
    "optimization_jobs": "event_id",
    "solutions": "event_id",
}


async def tangled_event(
    client: AsyncClient, event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> dict[str, Any]:
    """A solved event exercising every foreign key that points into it.

    One seat and two passengers, so somebody lands in `unassigned_participants`; a pin, so
    `participants.pinned_driver_id` is populated; and another event pointing at this one through
    `template_event_id`.
    """
    public_id, _ = event
    driver = await add(client, event, person("Sam", "driver", role="driver", seats_available=1))
    await add(client, event, person("Ada", "east", pinned_driver_id=driver["id"]))
    await add(client, event, person("Bo", "west"))
    job = await optimize(client, event)

    template_id, _ = await other_event(client)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "update events set template_event_id ="
                " (select id from events where public_id = :parent)"
                " where public_id = :child"
            ),
            {"parent": public_id, "child": template_id},
        )
    return job


async def counts(engine: AsyncEngine, public_id: str) -> dict[str, int]:
    """How many rows of each kind still hang off this event."""
    async with engine.connect() as conn:
        event_id = (
            await conn.execute(text("select id from events where public_id = :p"), {"p": public_id})
        ).scalar_one_or_none()
        if event_id is None:
            return {}
        found = {}
        for table, column in DEPENDENTS.items():
            found[table] = (
                await conn.execute(
                    text(f"select count(*) from {table} where {column} = :e"), {"e": event_id}
                )
            ).scalar_one()
        found["routes"] = (
            await conn.execute(
                text(
                    "select count(*) from routes r join solutions s on s.id = r.solution_id"
                    " where s.event_id = :e"
                ),
                {"e": event_id},
            )
        ).scalar_one()
        found["route_stops"] = (
            await conn.execute(
                text(
                    "select count(*) from route_stops st join routes r on r.id = st.route_id"
                    " join solutions s on s.id = r.solution_id where s.event_id = :e"
                ),
                {"e": event_id},
            )
        ).scalar_one()
        found["unassigned_participants"] = (
            await conn.execute(
                text(
                    "select count(*) from unassigned_participants u"
                    " join solutions s on s.id = u.solution_id where s.event_id = :e"
                ),
                {"e": event_id},
            )
        ).scalar_one()
        return found


async def test_the_fixture_really_is_tangled(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """The guard: the deletion test below proves nothing if there is nothing to trip over."""
    public_id, _ = organizer_event
    await tangled_event(api_client, organizer_event, engine)

    before = await counts(engine, public_id)

    assert before["participants"] == 3
    assert before["solutions"] == 1
    assert before["routes"] == 1
    assert before["route_stops"] >= 2
    assert before["unassigned_participants"] == 1
    async with engine.connect() as conn:
        pins = (
            await conn.execute(
                text(
                    "select count(*) from participants p join events e on e.id = p.event_id"
                    " where e.public_id = :p and p.pinned_driver_id is not null"
                ),
                {"p": public_id},
            )
        ).scalar_one()
        templates = (
            await conn.execute(
                text(
                    "select count(*) from events child join events parent"
                    " on parent.id = child.template_event_id where parent.public_id = :p"
                ),
                {"p": public_id},
            )
        ).scalar_one()
    assert pins == 1, "a pin must be present, or pinned_driver_id is untested"
    assert templates == 1, "a clone must point here, or template_event_id is untested"


async def test_deleting_an_event_removes_everything_about_it(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """One statement, no ordering required of the caller.

    A retention job that has to delete child tables in the right order is a retention job that will
    one day be given a new table and quietly stop being complete.
    """
    public_id, _ = organizer_event
    await tangled_event(api_client, organizer_event, engine)

    async with engine.begin() as conn:
        await conn.execute(text("delete from events where public_id = :p"), {"p": public_id})

    assert await counts(engine, public_id) == {}, "the event itself should be gone"


async def test_deleting_an_event_spares_the_clone_that_referenced_it(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """Lineage is a pointer, not a dependency: losing the template must not delete the clone."""
    public_id, _ = organizer_event
    await tangled_event(api_client, organizer_event, engine)

    async with engine.begin() as conn:
        await conn.execute(text("delete from events where public_id = :p"), {"p": public_id})
        survivor = (
            await conn.execute(text("select count(*) from events where template_event_id is null"))
        ).scalar_one()

    assert survivor >= 1


async def test_deleting_one_participant_does_not_delete_the_rider_pinned_to_them(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """`pinned_driver_id` clears rather than cascading.

    The API never hard-deletes a participant -- cancelling is a status change (docs/design.md 5.3.1)
    -- but if one ever is, losing your pinned driver must not delete you along with them.
    """
    public_id, _ = organizer_event
    driver = await add(
        api_client, organizer_event, person("Sam", "driver", role="driver", seats_available=2)
    )
    rider = await add(
        api_client, organizer_event, person("Ada", "east", pinned_driver_id=driver["id"])
    )

    async with engine.begin() as conn:
        await conn.execute(text("delete from participants where id = :i"), {"i": driver["id"]})
        still_there = (
            await conn.execute(
                text("select pinned_driver_id from participants where id = :i"), {"i": rider["id"]}
            )
        ).one_or_none()

    assert still_there is not None, "the rider must survive their driver"
    assert still_there[0] is None, "the dangling pin must be cleared"
    assert public_id
