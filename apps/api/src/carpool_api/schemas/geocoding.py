"""Geocoding payloads (docs/design.md 4.4, 7.2).

Latitude first, as everywhere in this API -- the provider speaks `[lng, lat]` and the adapter is the
only place that order is read (docs/design.md 4.4, trap on coordinate order).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from carpool_api.adapters.geocoding import Place, Resolution

#: A pasted roster is capped at the event participant limit; asking for more in one request is a
#: mistake or an attempt to spend the shared daily quota in a single call.
MAX_BATCH = 60

#: Below this an autocomplete query matches most of the country and wastes a call per keystroke.
MIN_QUERY = 3

QUERY_MAX = 300


class PlaceRead(BaseModel):
    address: str
    lat: float
    lng: float
    #: The provider's 0..1 score. Null for a cache hit, which was not re-scored.
    confidence: float | None
    #: True when the match is coarser than a street address -- a town centroid standing in for a
    #: house. The roster UI marks these; they are the errors the verification map exists to catch.
    is_approximate: bool

    @classmethod
    def of(cls, place: Place) -> PlaceRead:
        return cls(
            address=place.address,
            lat=place.lat,
            lng=place.lng,
            confidence=place.confidence,
            is_approximate=place.is_approximate,
        )


class GeocodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    addresses: list[str] = Field(min_length=1, max_length=MAX_BATCH)


class ResolutionRead(BaseModel):
    """One result, in the order asked for. `place` is null when nothing matched."""

    query: str
    place: PlaceRead | None
    from_cache: bool

    @classmethod
    def of(cls, resolution: Resolution) -> ResolutionRead:
        return cls(
            query=resolution.query,
            place=PlaceRead.of(resolution.place) if resolution.place else None,
            from_cache=resolution.from_cache,
        )


class GeocodeResponse(BaseModel):
    """Exactly one result per requested address, in the same order.

    The client lines these up against roster rows, so a shorter list would shift every address after
    a failure onto the wrong person.
    """

    results: list[ResolutionRead]


class SuggestionsResponse(BaseModel):
    suggestions: list[PlaceRead]
