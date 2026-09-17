"""Geocoding through openrouteservice, with `geocode_cache` in front of it.

**The provider key never reaches the browser.** Address entry is a frontend interaction, but a key
shipped to the client can be lifted by anyone who loads the page and spends the shared quota, so
every call goes through here (docs/design.md 4.4).

**Resolved coordinates are cached with a TTL, not stored.** That is what keeps the choice of
geocoder reversible: most providers' terms restrict building a permanent database of their output,
while short-lived caching is generally permitted (docs/design.md 5.2). A coordinate a *human*
placed is not provider output and lives on the participant row with `geocode_source = 'user'` --
never in here, and never overwritten by a later re-resolve.

The quota that binds first is geocoding, at 3,000/day and 100/min (docs/design.md 4.4), which is why
resolution is batched: a pasted roster is one request and one cache round trip rather than forty.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from carpool_api.adapters.addresses import normalize_address
from carpool_api.config import Settings
from carpool_api.models import GeocodeCache

PROVIDER = "ors"

#: Pelias scores every result 0..1. Below this the answer is usually a city centroid standing in
#: for a street address -- the silent, catastrophic failure the verification map exists to catch
#: (docs/design.md 7.2). Surfaced rather than returned as if it were an address.
LOW_CONFIDENCE = 0.5


class GeocodingUnavailable(Exception):
    """The provider could not be reached, or is not configured. Never a bad address."""


@dataclass(frozen=True, slots=True)
class Place:
    """One candidate location.

    `confidence` and `is_approximate` travel to the UI on purpose: a coordinator pasting forty
    addresses needs the three doubtful ones marked, not an interface that looks equally sure of all
    of them.
    """

    address: str
    lat: float
    lng: float
    #: The provider's 0..1 score, or None for a cache hit -- a cached coordinate was not re-scored,
    #: and inventing a number for it would be the one kind of lie this flag exists to prevent.
    confidence: float | None
    #: True when the provider matched something coarser than a street address.
    is_approximate: bool


def _parse_features(payload: object) -> list[Place]:
    """Read Pelias GeoJSON into `Place`s, skipping anything malformed.

    **Coordinates arrive as `[lng, lat]`.** A swap raises no error and produces no exception -- only
    drivers sent to the wrong place -- so the order is pinned by a test (docs/design.md 4.4).
    """
    if not isinstance(payload, dict):
        return []
    features = payload.get("features")
    if not isinstance(features, list):
        return []

    places: list[Place] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        properties = feature.get("properties")
        if not isinstance(geometry, dict) or not isinstance(properties, dict):
            continue
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        lng, lat = coordinates[0], coordinates[1]
        label = properties.get("label")
        if not isinstance(lng, int | float) or not isinstance(lat, int | float):
            continue
        if not isinstance(label, str):
            continue
        confidence = properties.get("confidence")
        confidence = float(confidence) if isinstance(confidence, int | float) else 0.0
        # Pelias `layer` says how coarse the match is. `address` and `venue` are precise enough to
        # pick someone up at; `locality` or `region` means it fell back to a town or a state.
        layer = properties.get("layer")
        places.append(
            Place(
                address=label,
                lat=float(lat),
                lng=float(lng),
                confidence=confidence,
                is_approximate=layer not in ("address", "venue") or confidence < LOW_CONFIDENCE,
            )
        )
    return places


class OrsGeocoder:
    """The provider client. Holds no session and writes nothing -- caching is layered on top."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def _params(self, **extra: str | int) -> dict[str, str | int]:
        if not self._settings.ors_api_key:
            raise GeocodingUnavailable("ORS_API_KEY is not configured")
        params: dict[str, str | int] = {"api_key": self._settings.ors_api_key, **extra}
        if self._settings.geocode_country:
            params["boundary.country"] = self._settings.geocode_country
        return params

    async def _get(self, path: str, params: dict[str, str | int]) -> list[Place]:
        timeout = self._settings.ors_timeout_seconds
        url = f"{self._settings.ors_base_url.rstrip('/')}{path}"
        try:
            if self._client is not None:
                response = await self._client.get(url, params=params, timeout=timeout)
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise GeocodingUnavailable(f"could not reach the geocoder: {exc}") from exc

        if response.status_code == 429:
            raise GeocodingUnavailable("the geocoder's rate limit was reached; try again shortly")
        if response.status_code >= 400:
            # The body can echo the query but never the key -- it is sent as a parameter and this
            # message goes into logs and, for 503s, to the client.
            raise GeocodingUnavailable(f"the geocoder returned {response.status_code}")
        try:
            return _parse_features(response.json())
        except ValueError as exc:
            raise GeocodingUnavailable("the geocoder returned a malformed response") from exc

    async def search(self, text: str, *, limit: int) -> list[Place]:
        """Resolve a complete address. Best match first."""
        return await self._get("/geocode/search", self._params(text=text, size=limit))

    async def autocomplete(self, text: str, *, limit: int) -> list[Place]:
        """Suggestions for a partial address, for a type-ahead."""
        return await self._get("/geocode/autocomplete", self._params(text=text, size=limit))


async def _cached(session: AsyncSession, keys: list[str]) -> dict[str, GeocodeCache]:
    """Unexpired cache rows for these normalized addresses, and eviction of the expired ones.

    Expired rows are deleted rather than refreshed in place: renewing an `expires_at` without
    re-asking the provider would quietly turn the cache into the permanent store of provider output
    that docs/design.md 5.2 is built to avoid.
    """
    if not keys:
        return {}
    now = datetime.now(UTC)
    rows = (
        await session.execute(select(GeocodeCache).where(GeocodeCache.address_norm.in_(keys)))
    ).scalars()

    fresh: dict[str, GeocodeCache] = {}
    stale: list[str] = []
    for row in rows:
        if row.expires_at > now:
            fresh[row.address_norm] = row
        else:
            stale.append(row.address_norm)
    if stale:
        await session.execute(delete(GeocodeCache).where(GeocodeCache.address_norm.in_(stale)))
    return fresh


async def _remember(session: AsyncSession, key: str, place: Place, ttl_seconds: int) -> None:
    """Upsert, because two requests geocoding the same address can race.

    Only confident, street-level matches reach here (see `resolve`). `geocode_cache` therefore holds
    coordinates that were precise when resolved, which is what lets a cache hit report
    `is_approximate = False` honestly without the table carrying a confidence column.

    `ON CONFLICT DO UPDATE` with the provider's fresh answer is a re-geocode, not a renewal -- the
    distinction that matters is that `expires_at` never moves without the provider being asked
    again.
    """
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    statement = insert(GeocodeCache).values(
        address_norm=key,
        lat=place.lat,
        lng=place.lng,
        provider=PROVIDER,
        expires_at=expires_at,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[GeocodeCache.address_norm],
            set_={
                "lat": statement.excluded.lat,
                "lng": statement.excluded.lng,
                "provider": statement.excluded.provider,
                "cached_at": datetime.now(UTC),
                "expires_at": statement.excluded.expires_at,
            },
        )
    )


@dataclass(frozen=True, slots=True)
class Resolution:
    """What one requested address resolved to. `place is None` means nothing matched."""

    query: str
    place: Place | None
    from_cache: bool


async def resolve(
    session: AsyncSession,
    geocoder: OrsGeocoder,
    addresses: list[str],
    *,
    ttl_seconds: int,
) -> list[Resolution]:
    """Resolve each address, reading the cache first and writing back what it had to fetch.

    Results come back in the order asked for, one per input, including the ones that failed to
    match: a roster paste lines results up against rows, and a silently shorter list would shift
    every address after the failure onto the wrong person.
    """
    keys = [normalize_address(address) for address in addresses]
    cached = await _cached(session, [key for key in keys if key])

    results: list[Resolution] = []
    for address, key in zip(addresses, keys, strict=True):
        row = cached.get(key)
        if row is not None:
            results.append(
                Resolution(
                    query=address,
                    # A cached row keeps coordinates only, so the label echoes what was asked. The
                    # provider's prettier label is not worth a second table.
                    place=Place(
                        address=address,
                        lat=row.lat,
                        lng=row.lng,
                        confidence=None,
                        is_approximate=False,
                    ),
                    from_cache=True,
                )
            )
            continue

        found = await geocoder.search(address, limit=1) if key else []
        place = found[0] if found else None
        # An approximate match is deliberately *not* cached. Caching it would mean a later request
        # reading back a coordinate with no record of how doubtful it was, and reporting it as
        # precise -- and a wrong coordinate the coordinator was never warned about is the failure
        # that distorts an entire solve (docs/design.md 7.2). Re-asking costs one geocode, and the
        # address is about to be corrected by hand anyway.
        if place is not None and key and not place.is_approximate:
            await _remember(session, key, place, ttl_seconds)
            cached[key] = GeocodeCache(
                address_norm=key,
                lat=place.lat,
                lng=place.lng,
                provider=PROVIDER,
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            )
        results.append(Resolution(query=address, place=place, from_cache=False))
    return results
