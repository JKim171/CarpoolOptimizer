"""Caches -- both deliberately caches, not stores (docs/design.md 5.2, 5.1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from carpool_api.models.base import Base


class GeocodeCache(Base):
    """Resolved coordinates with an explicit expiry.

    This is a performance cache with a TTL, never a permanent database of provider-returned
    coordinates -- that distinction is what keeps the choice of geocoder reversible under most
    providers' storage terms (docs/design.md 5.2). Rows are evicted on expiry, never renewed in
    place. A coordinate a *human* placed is not provider output and lives on the participant row
    instead, flagged `geocode_source = 'user'`.
    """

    __tablename__ = "geocode_cache"

    #: Normalized address string.
    address_norm: Mapped[str] = mapped_column(Text, primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(Text)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TravelCache(Base):
    """Pairwise travel times, keyed by spatial cell rather than by event.

    The matrix is never stored on a job row -- at n=1000 it is ~8 MB. Keying by cell pair means a
    club practising at the same venue every week shares cached entries across events, and the hit
    rate is a real measurable number (docs/design.md 5.1).
    """

    __tablename__ = "travel_cache"

    origin_cell: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dest_cell: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile: Mapped[str] = mapped_column(Text, primary_key=True)
    #: Integer seconds; ORS returns floats and they are rounded at the adapter boundary.
    duration_s: Mapped[int] = mapped_column(Integer)
    distance_m: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
