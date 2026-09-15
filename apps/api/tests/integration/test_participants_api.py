"""The roster endpoints against a real Postgres (docs/design.md 6, 5.1, 5.3).

The cap tests are the reason this file exists against a container rather than a stub. A participant
cap that is only ever tested one request at a time proves nothing: the failure mode is two callers
both seeing 49 free seats, which requires real transactions and a real row lock to reproduce.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from carpool_api.limits import MAX_ACTIVE_PARTICIPANTS

# Ann Arbor again -- latitude positive, longitude negative, so a swap cannot hide.
LAT = 42.2936
LNG = -83.7101


def rider(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "display_name": "Jordan Alvarez",
        "pickup": {"address": "721 S Forest Ave, Ann Arbor, MI", "lat": LAT, "lng": LNG},
        "role": "passenger",
    }
    body.update(overrides)
    return body


def driver(**overrides: Any) -> dict[str, Any]:
    return rider(display_name="Sam Okafor", role="driver", seats_available=3, **overrides)


async def add(
    client: AsyncClient,
    event: tuple[str, dict[str, str]],
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    public_id, headers = event
    response = await client.post(
        f"/v1/events/{public_id}/participants", headers=headers, json=body or rider()
    )
    assert response.status_code == 201, response.text
    return response.json()


async def roster(client: AsyncClient, event: tuple[str, dict[str, str]]) -> dict[str, Any]:
    public_id, headers = event
    response = await client.get(f"/v1/events/{public_id}/participants", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_add_returns_the_participant_and_the_new_version(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event

    response = await api_client.post(
        f"/v1/events/{public_id}/participants", headers=headers, json=driver()
    )

    assert response.status_code == 201, response.text
    written = response.json()
    assert written["participants_version"] == 1
    person = written["participant"]
    assert person["display_name"] == "Sam Okafor"
    assert person["role"] == "driver"
    assert person["seats_available"] == 3
    assert person["status"] == "active"
    assert person["pickup"] == {
        "address": "721 S Forest Ave, Ann Arbor, MI",
        "lat": LAT,
        "lng": LNG,
    }
    assert response.headers["Location"] == (f"/v1/events/{public_id}/participants/{person['id']}")


async def test_each_add_bumps_the_roster_version(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """The version is what tells a client its solution is stale (docs/design.md 5.1)."""
    versions = [(await add(api_client, organizer_event))["participants_version"] for _ in range(3)]

    assert versions == [1, 2, 3]
    assert (await roster(api_client, organizer_event))["participants_version"] == 3


async def test_the_participant_token_is_not_returned_but_is_stored_hashed(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """Minted because the column is not-null; withheld because no endpoint accepts one yet."""
    written = await add(api_client, organizer_event)

    assert "token" not in str(written).lower().replace("token_hash", "")
    async with engine.connect() as conn:
        hashes = (
            await conn.execute(
                text("select token_hash from participants where id = :i"),
                {"i": written["participant"]["id"]},
            )
        ).scalars()
        stored = list(hashes)

    assert len(stored) == 1
    assert len(stored[0]) == 32


async def test_participants_get_distinct_tokens(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """`token_hash` is unique across the table, so a shared one would be a hard insert failure."""
    await add(api_client, organizer_event)
    await add(api_client, organizer_event, rider(display_name="Priya Raman"))

    async with engine.connect() as conn:
        stored = (
            await conn.execute(text("select distinct token_hash from participants"))
        ).scalars()

    assert len(set(stored)) >= 2


async def test_roster_is_listed_in_entry_order(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    for name in ("First", "Second", "Third"):
        await add(api_client, organizer_event, rider(display_name=name))

    listed = await roster(api_client, organizer_event)

    assert [p["display_name"] for p in listed["participants"]] == ["First", "Second", "Third"]


async def test_a_participant_can_be_read_individually(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    written = await add(api_client, organizer_event)

    response = await api_client.get(
        f"/v1/events/{public_id}/participants/{written['participant']['id']}", headers=headers
    )

    assert response.status_code == 200
    assert response.json() == written["participant"]


async def test_a_participant_of_another_event_is_not_reachable(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """Every lookup is scoped by event_id; a guessable id must not be enough."""
    public_id, headers = organizer_event
    mine = await add(api_client, organizer_event)

    other = await api_client.post(
        "/v1/events",
        json={
            "name": "Another event",
            "destination": {"address": "1 Main St", "lat": 42.0, "lng": -83.0},
            "arrival_at": "2026-10-01T16:00:00-04:00",
            "ends_at": "2026-10-01T18:00:00-04:00",
            "timezone": "America/Detroit",
        },
    )
    other_body = other.json()
    theirs = await add(
        api_client,
        (
            other_body["event"]["public_id"],
            {"Authorization": f"Bearer {other_body['organizer_token']}"},
        ),
    )

    response = await api_client.get(
        f"/v1/events/{public_id}/participants/{theirs['participant']['id']}", headers=headers
    )

    assert response.status_code == 404
    assert mine["participant"]["id"] != theirs["participant"]["id"]


async def test_roster_endpoints_require_the_organizer_token(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, _ = organizer_event

    added = await api_client.post(f"/v1/events/{public_id}/participants", json=rider())
    listed = await api_client.get(f"/v1/events/{public_id}/participants")

    assert added.status_code == 401
    assert listed.status_code == 401


async def test_a_passenger_cannot_have_seats(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """A data-entry mistake with a correct alternative: the `either` role exists for this."""
    public_id, headers = organizer_event

    response = await api_client.post(
        f"/v1/events/{public_id}/participants",
        headers=headers,
        json=rider(role="passenger", seats_available=4),
    )

    assert response.status_code == 422
    assert "either" in response.text


async def test_the_dormant_either_role_is_accepted(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """`Role.EITHER` is dormant by decision, not dead code (CLAUDE.md) -- the API still takes it."""
    written = await add(api_client, organizer_event, rider(role="either", seats_available=2))

    assert written["participant"]["role"] == "either"


async def test_a_participant_must_need_at_least_one_leg(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event

    response = await api_client.post(
        f"/v1/events/{public_id}/participants",
        headers=headers,
        json=rider(needs_outbound=False, needs_return=False),
    )

    assert response.status_code == 422


async def test_a_pin_must_name_a_driver_on_this_event(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    passenger = await add(api_client, organizer_event)

    response = await api_client.post(
        f"/v1/events/{public_id}/participants",
        headers=headers,
        json=rider(pinned_driver_id=passenger["participant"]["id"]),
    )

    assert response.status_code == 422
    assert "drives" in response.text


async def test_a_pin_to_an_unknown_participant_is_rejected(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """The foreign key cannot express "on the same event"; the solver would strand the rider."""
    public_id, headers = organizer_event

    response = await api_client.post(
        f"/v1/events/{public_id}/participants",
        headers=headers,
        json=rider(pinned_driver_id="00000000-0000-0000-0000-000000000001"),
    )

    assert response.status_code == 422


async def test_a_valid_pin_is_stored(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    wheels = await add(api_client, organizer_event, driver())

    pinned = await add(
        api_client, organizer_event, rider(pinned_driver_id=wheels["participant"]["id"])
    )

    assert pinned["participant"]["pinned_driver_id"] == wheels["participant"]["id"]


async def test_patch_updates_fields_and_bumps_the_version(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    written = await add(api_client, organizer_event)
    before = written["participant"]

    response = await api_client.patch(
        f"/v1/events/{public_id}/participants/{before['id']}",
        headers=headers,
        json={"display_name": "Jordan A.", "priority": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["participants_version"] == 2
    assert body["participant"]["display_name"] == "Jordan A."
    assert body["participant"]["priority"] == 3
    assert datetime.fromisoformat(body["participant"]["updated_at"]) >= datetime.fromisoformat(
        before["updated_at"]
    )


async def test_patch_moves_the_pickup_as_a_unit(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    written = await add(api_client, organizer_event)

    response = await api_client.patch(
        f"/v1/events/{public_id}/participants/{written['participant']['id']}",
        headers=headers,
        json={"pickup": {"address": "1100 Baits Dr, Ann Arbor, MI", "lat": 42.29, "lng": -83.72}},
    )

    assert response.status_code == 200
    assert response.json()["participant"]["pickup"] == {
        "address": "1100 Baits Dr, Ann Arbor, MI",
        "lat": 42.29,
        "lng": -83.72,
    }


async def test_patch_rejects_a_pickup_without_coordinates(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    written = await add(api_client, organizer_event)

    response = await api_client.patch(
        f"/v1/events/{public_id}/participants/{written['participant']['id']}",
        headers=headers,
        json={"pickup": {"address": "1100 Baits Dr, Ann Arbor, MI"}},
    )

    assert response.status_code == 422


async def test_patch_cannot_leave_a_passenger_holding_seats(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """One field, valid alone, invalid in combination with what is already stored."""
    public_id, headers = organizer_event
    wheels = await add(api_client, organizer_event, driver())

    response = await api_client.patch(
        f"/v1/events/{public_id}/participants/{wheels['participant']['id']}",
        headers=headers,
        json={"role": "passenger"},
    )

    assert response.status_code == 422


async def test_patch_can_clear_an_optional_field_with_null(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """Sending `null` has to differ from not mentioning the field -- this is the removal path."""
    public_id, headers = organizer_event
    wheels = await add(api_client, organizer_event, driver())
    pinned = await add(
        api_client, organizer_event, rider(pinned_driver_id=wheels["participant"]["id"])
    )

    response = await api_client.patch(
        f"/v1/events/{public_id}/participants/{pinned['participant']['id']}",
        headers=headers,
        json={"pinned_driver_id": None},
    )

    assert response.status_code == 200
    assert response.json()["participant"]["pinned_driver_id"] is None


async def test_cancel_is_a_status_change_not_a_delete(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]], engine: AsyncEngine
) -> None:
    """A solution already computed still refers to this row (docs/design.md 5.3.1)."""
    public_id, headers = organizer_event
    written = await add(api_client, organizer_event)
    participant_id = written["participant"]["id"]

    response = await api_client.delete(
        f"/v1/events/{public_id}/participants/{participant_id}", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["participant"]["status"] == "cancelled"
    async with engine.connect() as conn:
        status_value = (
            await conn.execute(
                text("select status from participants where id = :i"), {"i": participant_id}
            )
        ).scalar_one()
    assert status_value == "cancelled"


async def test_a_cancelled_participant_leaves_the_roster_but_stays_readable(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    written = await add(api_client, organizer_event)
    participant_id = written["participant"]["id"]
    await api_client.delete(
        f"/v1/events/{public_id}/participants/{participant_id}", headers=headers
    )

    listed = await roster(api_client, organizer_event)
    fetched = await api_client.get(
        f"/v1/events/{public_id}/participants/{participant_id}", headers=headers
    )

    assert listed["participants"] == []
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "cancelled"


async def test_cancel_is_idempotent_and_does_not_move_the_version(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    written = await add(api_client, organizer_event)
    url = f"/v1/events/{public_id}/participants/{written['participant']['id']}"

    first = await api_client.delete(url, headers=headers)
    second = await api_client.delete(url, headers=headers)

    assert first.json()["participants_version"] == 2
    assert second.status_code == 200
    assert second.json()["participants_version"] == 2


async def test_cancelling_a_driver_clears_pins_pointing_at_them(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """Otherwise the solver holds a constraint naming someone who is not coming."""
    public_id, headers = organizer_event
    wheels = await add(api_client, organizer_event, driver())
    pinned = await add(
        api_client, organizer_event, rider(pinned_driver_id=wheels["participant"]["id"])
    )

    await api_client.delete(
        f"/v1/events/{public_id}/participants/{wheels['participant']['id']}", headers=headers
    )

    remaining = await api_client.get(
        f"/v1/events/{public_id}/participants/{pinned['participant']['id']}", headers=headers
    )
    assert remaining.json()["pinned_driver_id"] is None


async def test_a_cancelled_participant_cannot_be_edited(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    written = await add(api_client, organizer_event)
    url = f"/v1/events/{public_id}/participants/{written['participant']['id']}"
    await api_client.delete(url, headers=headers)

    response = await api_client.patch(url, headers=headers, json={"display_name": "Back again"})

    assert response.status_code == 409


async def test_a_locked_event_refuses_roster_changes(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """Locking freezes the roster -- that is the whole point of it."""
    public_id, headers = organizer_event
    written = await add(api_client, organizer_event)
    participant_id = written["participant"]["id"]
    await api_client.post(f"/v1/events/{public_id}/lock", headers=headers)

    added = await api_client.post(
        f"/v1/events/{public_id}/participants", headers=headers, json=rider()
    )
    patched = await api_client.patch(
        f"/v1/events/{public_id}/participants/{participant_id}",
        headers=headers,
        json={"priority": 1},
    )
    cancelled = await api_client.delete(
        f"/v1/events/{public_id}/participants/{participant_id}", headers=headers
    )
    listed = await api_client.get(f"/v1/events/{public_id}/participants", headers=headers)

    assert added.status_code == 409
    assert patched.status_code == 409
    assert cancelled.status_code == 409
    assert listed.status_code == 200, "reading a locked roster is still fine"


async def test_the_cap_rejects_the_participant_past_the_limit(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    for index in range(MAX_ACTIVE_PARTICIPANTS):
        await add(api_client, organizer_event, rider(display_name=f"Rider {index}"))

    response = await api_client.post(
        f"/v1/events/{public_id}/participants", headers=headers, json=rider(display_name="One more")
    )

    assert response.status_code == 422
    assert str(MAX_ACTIVE_PARTICIPANTS) in response.text


async def test_a_rejected_add_leaves_no_trace(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """The version bump and the insert are undone together.

    A version that moved for a participant who was refused would make every existing solution look
    stale for no reason.
    """
    public_id, headers = organizer_event
    for index in range(MAX_ACTIVE_PARTICIPANTS):
        await add(api_client, organizer_event, rider(display_name=f"Rider {index}"))

    await api_client.post(
        f"/v1/events/{public_id}/participants", headers=headers, json=rider(display_name="Refused")
    )

    listed = await roster(api_client, organizer_event)
    assert listed["participants_version"] == MAX_ACTIVE_PARTICIPANTS
    assert len(listed["participants"]) == MAX_ACTIVE_PARTICIPANTS


async def test_cancelling_returns_a_seat_to_the_cap(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    public_id, headers = organizer_event
    first = await add(api_client, organizer_event, rider(display_name="Rider 0"))
    for index in range(1, MAX_ACTIVE_PARTICIPANTS):
        await add(api_client, organizer_event, rider(display_name=f"Rider {index}"))

    await api_client.delete(
        f"/v1/events/{public_id}/participants/{first['participant']['id']}", headers=headers
    )
    response = await api_client.post(
        f"/v1/events/{public_id}/participants", headers=headers, json=rider(display_name="Late add")
    )

    assert response.status_code == 201
    assert len((await roster(api_client, organizer_event))["participants"]) == (
        MAX_ACTIVE_PARTICIPANTS
    )


async def test_concurrent_adds_cannot_both_take_the_last_seat(
    api_client: AsyncClient, organizer_event: tuple[str, dict[str, str]]
) -> None:
    """The race the cap exists to survive (docs/design.md 5.1).

    Ten requests arrive together for five remaining seats. Every one of them reads the roster count,
    so if the version bump were not serializing them on the event row, more than five would see room
    and the event would end up over the cap. Exactly five must win.
    """
    public_id, headers = organizer_event
    free_seats = 5
    for index in range(MAX_ACTIVE_PARTICIPANTS - free_seats):
        await add(api_client, organizer_event, rider(display_name=f"Rider {index}"))

    responses = await asyncio.gather(
        *(
            api_client.post(
                f"/v1/events/{public_id}/participants",
                headers=headers,
                json=rider(display_name=f"Racer {index}"),
            )
            for index in range(free_seats * 2)
        )
    )

    codes = sorted(response.status_code for response in responses)
    assert codes == [201] * free_seats + [422] * free_seats
    listed = await roster(api_client, organizer_event)
    assert len(listed["participants"]) == MAX_ACTIVE_PARTICIPANTS
    assert listed["participants_version"] == MAX_ACTIVE_PARTICIPANTS
