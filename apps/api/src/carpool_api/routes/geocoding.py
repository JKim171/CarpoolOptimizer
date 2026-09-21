"""Geocoding endpoints (docs/design.md 4.4).

A thin proxy in front of openrouteservice whose only job is to keep the provider key on the server.
Address entry is a frontend interaction, but a key in the browser bundle can be lifted by anyone who
loads the page and spent against the shared quota.

**These endpoints are deliberately unauthenticated, and that is a bounded decision, not an
oversight.** The create-event screen geocodes a destination *before* an event exists, so there is no
organizer token to require yet -- gating them would mean no address entry on the first screen. What
they expose is a proxied provider quota, not any event data: nothing here reads or writes a
participant, and an attacker learns only what the public geocoder would already tell them.

What that costs is quota. The daily geocoding allowance (3,000/day, 100/min) is shared across the
whole deployment, so an unauthenticated caller could exhaust it and stop roster entry working for
everyone. Hence the per-client limits in `carpool_api.ratelimit`: lookups that reach the provider
are counted per client per day, and autocomplete per minute.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from carpool_api.adapters.geocoding import GeocodingUnavailable, OrsGeocoder, resolve
from carpool_api.config import Settings, get_settings
from carpool_api.db import get_session
from carpool_api.ratelimit import AUTOCOMPLETE, GEOCODE_LOOKUPS, Limiter, client_key, limit
from carpool_api.schemas.geocoding import (
    MIN_QUERY,
    QUERY_MAX,
    GeocodeRequest,
    GeocodeResponse,
    PlaceRead,
    ResolutionRead,
    SuggestionsResponse,
)

router = APIRouter(prefix="/v1/geocode", tags=["geocoding"])

Session = Annotated[AsyncSession, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


def get_geocoder(settings: Config) -> OrsGeocoder:
    """The provider client, as a dependency so tests can substitute one that makes no network call.

    Built per request rather than once per process: it is a thin wrapper over settings and holds no
    connection pool of its own, and a module-level instance would capture settings at import time.
    """
    return OrsGeocoder(settings)


Geocoder = Annotated[OrsGeocoder, Depends(get_geocoder)]

#: Enough to choose from without turning a type-ahead into a scrolling list.
SUGGESTION_LIMIT = 5


def _unavailable(exc: GeocodingUnavailable) -> HTTPException:
    """503, never 500.

    The geocoder being down, rate limited or unconfigured is a dependency failing, not this service
    breaking, and the client's correct response is to let the coordinator place the pin by hand and
    carry on -- which the UI supports, because coordinates may always be supplied directly
    (docs/design.md 5.2).
    """
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post("", response_model=GeocodeResponse)
async def geocode(
    body: GeocodeRequest,
    request: Request,
    session: Session,
    settings: Config,
    geocoder: Geocoder,
    limiter: Limiter,
) -> GeocodeResponse:
    """Resolve a batch of complete addresses, cache-first.

    Batched because a pasted roster is the case that matters: forty addresses as forty requests is
    forty round trips and forty cache queries, against a provider limited to 100 calls a minute.
    """
    try:
        resolutions = await resolve(
            session,
            geocoder,
            body.addresses,
            ttl_seconds=settings.geocode_ttl_seconds,
            # Charged once the cache has been read, for the lookups that will reach the provider.
            spend=lambda lookups: limiter.hit(GEOCODE_LOOKUPS, client_key(request), lookups),
        )
    except GeocodingUnavailable as exc:
        raise _unavailable(exc) from exc

    # The cache writes are part of this transaction and nothing else in the request writes, so the
    # commit is here rather than in the adapter -- the adapter stays callable from inside a larger
    # unit of work, which is what the Week 4 solve-time geocoding will need.
    await session.commit()
    return GeocodeResponse(results=[ResolutionRead.of(item) for item in resolutions])


@router.get(
    "/autocomplete",
    response_model=SuggestionsResponse,
    dependencies=[Depends(limit(AUTOCOMPLETE))],
)
async def autocomplete(
    geocoder: Geocoder,
    q: Annotated[str, Query(min_length=MIN_QUERY, max_length=QUERY_MAX)],
) -> SuggestionsResponse:
    """Suggestions for a partial address.

    **Not cached.** `geocode_cache` is keyed by a full normalized address; a prefix is not one, and
    storing every keystroke would fill the table with strings no one will ever look up again. The
    address the coordinator actually picks is resolved through `POST /v1/geocode`, which is cached.
    """
    try:
        places = await geocoder.autocomplete(q, limit=SUGGESTION_LIMIT)
    except GeocodingUnavailable as exc:
        raise _unavailable(exc) from exc
    return SuggestionsResponse(suggestions=[PlaceRead.of(place) for place in places])
