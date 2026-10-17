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

from collections.abc import Sequence
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


def line(coordinates: Sequence[tuple[float, float]]) -> WKTElement:
    """A line for a `geometry(LINESTRING)` column, from `[lng, lat]` pairs -- already WKT's order,
    so nothing is swapped here."""
    return WKTElement(
        "LINESTRING(" + ", ".join(f"{lng} {lat}" for lng, lat in coordinates) + ")", srid=SRID
    )


def simplified_geojson(
    column: ColumnExpressionArgument[Any], tolerance_degrees: float
) -> ColumnElement[str | None]:
    """SQL expression for a line column as GeoJSON, with points closer than the tolerance merged.

    Six decimal places is about 10 cm, finer than anything a map draws; the precision argument is
    there so a coordinate does not travel as seventeen digits of float noise.
    """
    return func.ST_AsGeoJSON(func.ST_SimplifyPreserveTopology(column, tolerance_degrees), 6)
