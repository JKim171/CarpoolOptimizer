"""Building a `ProblemInstance` out of an event and its roster.

This is the only place database rows become domain objects, and every conversion it performs is one
that fails silently if it is wrong:

* participant UUIDs become string node ids (the domain's `DESTINATION` sentinel cannot collide with
  a UUID's text form, which is what makes a bare string safe as a node id);
* `timestamptz` becomes **epoch seconds**, the one time unit the domain uses (CLAUDE.md);
* `max_detour_minutes` becomes `max_detour_seconds` -- the schema stores what an organizer types,
  the solver uses the unit everything else is in;
* cancelled participants are dropped, so they neither count nor get routed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from carpool_api.adapters.travel import TravelEstimates, haversine_estimates
from carpool_api.geo import latitude_of, longitude_of
from carpool_api.models import Event, Participant, ParticipantRole, ParticipantStatus
from carpool_api.schemas.weights import Weights
from carpool_domain import (
    DESTINATION,
    Location,
    NodeId,
    ProblemInstance,
    Role,
)
from carpool_domain import (
    Participant as DomainParticipant,
)


class MissingCoordinates(Exception):
    """A participant on the roster has no usable coordinates.

    Until Week 4 the API requires the caller to supply them, so this means a row predating that
    rule or written by hand. Once geocoding exists this becomes an unroutable-point case resolved
    before the solve, not an error -- which is why it is a named exception rather than an assertion.
    """

    def __init__(self, participant_ids: Sequence[str]) -> None:
        self.participant_ids = tuple(participant_ids)
        super().__init__(f"no coordinates for participant(s): {', '.join(self.participant_ids)}")


class EstimatesFor(Protocol):
    """The routing seam. Week 4 passes an openrouteservice-backed implementation instead."""

    def __call__(self, nodes: Mapping[NodeId, Location]) -> TravelEstimates: ...


@dataclass(frozen=True, slots=True)
class LoadedInstance:
    """A solvable instance, plus what is needed to write its answer back.

    `rows` keeps the mapping from node id to the participant row it came from, so persisting a
    solution never has to re-query or parse a UUID back out of a node id.
    """

    instance: ProblemInstance
    estimates: TravelEstimates
    rows: Mapping[NodeId, Participant]

    @property
    def drivers(self) -> int:
        return sum(1 for p in self.instance.participants if p.role.can_drive)


def _epoch(moment: datetime | None) -> int | None:
    return None if moment is None else int(moment.timestamp())


_ROLES = {
    ParticipantRole.DRIVER: Role.DRIVER,
    ParticipantRole.PASSENGER: Role.PASSENGER,
    ParticipantRole.EITHER: Role.EITHER,
}


async def active_roster(
    session: AsyncSession, event: Event
) -> list[tuple[Participant, float | None, float | None]]:
    """The active roster with coordinates, in a stable order.

    Ordered by id rather than by entry time: the solver's tie-breaking reads participant ids, so a
    stable order makes a re-solve of an unchanged roster produce a byte-identical answer. That is
    what makes `input_fingerprint`-based reuse meaningful rather than approximately true.
    """
    found = await session.execute(
        select(
            Participant,
            latitude_of(Participant.pickup_geog),
            longitude_of(Participant.pickup_geog),
        )
        .where(
            Participant.event_id == event.id,
            Participant.status == ParticipantStatus.ACTIVE,
        )
        .order_by(Participant.id)
    )
    return [(row[0], row[1], row[2]) for row in found.all()]


def build_instance(
    event: Event,
    roster: Sequence[tuple[Participant, float | None, float | None]],
    destination: Location,
    *,
    weights: Weights,
    estimates_for: EstimatesFor = haversine_estimates,
) -> LoadedInstance:
    """Assemble the instance. Pure given its inputs -- the querying is `active_roster`'s job."""
    missing = [str(row.id) for row, lat, lng in roster if lat is None or lng is None]
    if missing:
        raise MissingCoordinates(missing)

    rows = {str(row.id): row for row, _, _ in roster}
    nodes: dict[NodeId, Location] = {DESTINATION: destination}
    participants = []
    for row, lat, lng in roster:
        node_id = str(row.id)
        # Guarded above; the narrowing is for the type checker, which cannot see it.
        assert lat is not None
        assert lng is not None
        nodes[node_id] = Location(lat=lat, lng=lng)
        participants.append(
            DomainParticipant(
                id=node_id,
                location=Location(lat=lat, lng=lng),
                role=_ROLES[row.role],
                seats=row.seats_available,
                priority=row.priority,
                earliest_departure=_epoch(row.earliest_departure),
                latest_arrival=_epoch(row.latest_arrival),
                max_detour_seconds=(
                    None if row.max_detour_minutes is None else row.max_detour_minutes * 60
                ),
                pinned_driver_id=(
                    None if row.pinned_driver_id is None else str(row.pinned_driver_id)
                ),
                needs_outbound=row.needs_outbound,
                needs_return=row.needs_return,
            )
        )

    estimates = estimates_for(nodes)
    instance = ProblemInstance(
        destination=destination,
        arrival_by=int(event.arrival_at.timestamp()),
        ends_at=int(event.ends_at.timestamp()),
        participants=tuple(participants),
        matrix=estimates.matrix,
        weights=weights.to_domain(),
    )
    return LoadedInstance(instance=instance, estimates=estimates, rows=rows)
