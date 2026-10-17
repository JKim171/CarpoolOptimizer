"""Road geometry for one leg of one car, from openrouteservice Directions (docs/design.md 4.4, 7.5).

**Fetched lazily, once, then stored.** Drawing a route costs one Directions request per car per leg
-- about 30 for a 50-person event, against a quota of 2,000/day and 40/min. Spending that on every
solve would cap the whole deployment at a few dozen solves a day, and most solves are never looked
at: an organizer re-optimizes several times and drives one answer. So geometry is fetched the
first time a solution is viewed and persisted on the route, and every later view is a database
read.

A leg the provider cannot draw stays null, and the map draws that one as straight lines between
stops -- the same picture it showed before any geometry existed. A missing line is a worse picture,
never a wrong answer: the ordering, the times and the distances all come from the matrix, not from
here.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from carpool_api.adapters.travel import TravelUnavailable
from carpool_api.config import Settings
from carpool_domain import Location

_DIRECTIONS_PATH = "/openrouteservice/v2/directions/driving-car/geojson"

#: [lng, lat], as GeoJSON and the provider both order them.
Coordinate = tuple[float, float]


def parse_line(payload: object) -> list[Coordinate]:
    """The route's LineString out of a Directions GeoJSON response."""
    if not isinstance(payload, dict):
        raise TravelUnavailable("the directions response is not an object")
    features = payload.get("features")
    if not isinstance(features, list) or not features or not isinstance(features[0], dict):
        raise TravelUnavailable("the directions response has no route")
    geometry = features[0].get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        raise TravelUnavailable("the directions response has no line")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise TravelUnavailable("the directions response has too short a line")
    line: list[Coordinate] = []
    for point in coordinates:
        if (
            not isinstance(point, list)
            or len(point) < 2
            or not all(isinstance(value, int | float) for value in point[:2])
        ):
            raise TravelUnavailable("the directions response has a malformed point")
        line.append((float(point[0]), float(point[1])))
    return line


class OrsDirections:
    """The provider client. Holds no session and writes nothing -- storing is the caller's."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    async def line(self, stops: Sequence[Location]) -> list[Coordinate]:
        """The road path through `stops`, in order."""
        if not self._settings.ors_api_key:
            raise TravelUnavailable("ORS_API_KEY is not configured")
        # Longitude first, as in the matrix request; a swap fails silently there too.
        body: dict[str, object] = {
            "coordinates": [[stop.lng, stop.lat] for stop in stops],
            # Snap each waypoint to the nearest road however far away it is. The default refuses
            # anything beyond 350 m, which the matrix does not -- so a home at the end of a long
            # drive would get road times and then no line.
            "radiuses": [-1] * len(stops),
        }
        headers = {"Authorization": self._settings.ors_api_key}
        timeout = self._settings.ors_timeout_seconds
        url = f"{self._settings.ors_base_url.rstrip('/')}{_DIRECTIONS_PATH}"
        try:
            if self._client is not None:
                response = await self._client.post(url, json=body, headers=headers, timeout=timeout)
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise TravelUnavailable(f"could not reach the routing provider: {exc}") from exc

        if response.status_code >= 400:
            # The body is never quoted: it can echo the request, which holds home coordinates.
            raise TravelUnavailable(f"the routing provider returned {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TravelUnavailable("the routing provider returned a malformed response") from exc
        return parse_line(payload)
