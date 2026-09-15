"""Converting between latitude/longitude pairs and PostGIS point columns.

**Coordinate order is the entire reason this module exists.** Latitude-first is how humans and this
API's JSON write a point; WKT, GeoJSON and openrouteservice are all longitude-first. A swap raises
no error anywhere -- it silently relocates people, usually to somewhere plausible -- so the two
orderings meet in exactly these two functions, and both are pinned by tests.

Reading uses PostGIS rather than a Python geometry library: `ST_X`/`ST_Y` in the select is one round
trip and keeps `shapely` (and GEOS with it) out of the production image, for a job that is two
floats wide.
"""

from __future__ import annotations

from typing import Any

from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import ColumnElement, ColumnExpressionArgument, Float, cast, func

#: WGS 84 -- plain latitude/longitude, the only reference system in this system.
SRID = 4326


def point(lat: float, lng: float) -> WKTElement:
    """A point for writing to a `geography(POINT)` column. WKT is `POINT(lng lat)`."""
    return WKTElement(f"POINT({lng} {lat})", srid=SRID)


def latitude_of(column: ColumnExpressionArgument[Any]) -> ColumnElement[float]:
    """SQL expression for a point column's latitude -- the *Y* ordinate."""
    return cast(func.ST_Y(cast(column, Geometry)), Float)


def longitude_of(column: ColumnExpressionArgument[Any]) -> ColumnElement[float]:
    """SQL expression for a point column's longitude -- the *X* ordinate."""
    return cast(func.ST_X(cast(column, Geometry)), Float)
