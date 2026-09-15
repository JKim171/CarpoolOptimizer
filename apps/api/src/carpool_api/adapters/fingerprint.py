"""The content fingerprint that makes re-solving idempotent (docs/design.md 5.1).

A fingerprint matching an already-succeeded job means the answer is already computed, so the request
returns it instead of solving again. That makes client retries safe and makes re-running an
unchanged event instant.

**It is taken over address strings, never coordinates.** Geocoders drift: the same address can
resolve a metre differently next month, which would change the fingerprint of an event nobody had
touched and silently defeat the whole mechanism (docs/design.md 5.2).

What is included is exactly what changes the answer. `display_name`, `email`, `phone` and `notes`
are excluded on purpose -- correcting a spelling must not invalidate a solution. Participant ids
*are* included, so two people at the same address stay distinct and a cancel-then-re-add counts as a
change.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from carpool_api.adapters.addresses import normalize_address
from carpool_api.models import Event, Participant
from carpool_api.schemas.weights import Weights

#: Bumped if the fields below ever change meaning, so that old fingerprints cannot collide with new
#: ones computed from the same event. Cheaper than a migration that recomputes them.
FINGERPRINT_VERSION = 1


def _epoch(moment: datetime | None) -> int | None:
    return None if moment is None else int(moment.timestamp())


def input_fingerprint(
    event: Event,
    roster: Sequence[Participant],
    *,
    algorithm: str,
    weights: Weights,
) -> bytes:
    """SHA-256 over a canonical rendering of the problem.

    Canonical means sorted keys, participants sorted by id, and integer seconds rather than
    formatted timestamps -- so the same event fingerprints identically across processes, locales
    and Python versions. `json.dumps` with `sort_keys` and no whitespace is the whole trick.
    """
    payload: dict[str, Any] = {
        "v": FINGERPRINT_VERSION,
        "algorithm": algorithm,
        "weights": weights.model_dump(),
        "destination": normalize_address(event.destination_address),
        "arrival_at": int(event.arrival_at.timestamp()),
        "ends_at": int(event.ends_at.timestamp()),
        "participants": sorted(
            (
                {
                    "id": str(row.id),
                    "pickup": normalize_address(row.pickup_address),
                    "role": row.role.value,
                    "seats": row.seats_available,
                    "priority": row.priority,
                    "pinned_driver_id": (
                        None if row.pinned_driver_id is None else str(row.pinned_driver_id)
                    ),
                    "needs_outbound": row.needs_outbound,
                    "needs_return": row.needs_return,
                    "earliest_departure": _epoch(row.earliest_departure),
                    "latest_arrival": _epoch(row.latest_arrival),
                    "max_detour_minutes": row.max_detour_minutes,
                }
                for row in roster
            ),
            key=lambda entry: str(entry["id"]),
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).digest()
