"""Runtime configuration, read from the environment.

Every value comes from the process environment or `.env`, which is gitignored. Nothing here carries
a credential as a default -- not even the local development password, which lives in
`docker-compose.yml` and `.env.example` instead. See CLAUDE.md, "Never write secrets outside .env".
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    #: SQLAlchemy URL for the async driver, e.g. postgresql+asyncpg://user:pass@host:5432/carpool
    database_url: str

    #: openrouteservice key. Used by the geocoding proxy; the matrix adapter joins it in Week 4
    #: (docs/design.md 4.4). Optional so that the app still starts without it -- the geocoding
    #: endpoints then answer 503 rather than the whole service failing to boot.
    ors_api_key: str | None = None

    #: `api.openrouteservice.org` is deprecated in favour of this one (docs/design.md 4.4). In
    #: config rather than code so a base-URL change is a deploy, not a release.
    ors_base_url: str = Field(default="https://api.heigit.org")

    #: Seconds before a cached geocode is re-resolved. `geocode_cache` is a performance cache with
    #: an explicit TTL, never a permanent database of provider output -- that distinction is what
    #: keeps the choice of geocoder reversible under most providers' storage terms
    #: (docs/design.md 5.2). 30 days is the most restrictive cap in common use.
    geocode_ttl_seconds: int = Field(default=30 * 24 * 3600)

    #: Biases and restricts geocoding to one country. The product is a US site (docs/design.md 2.4);
    #: without this, "Springfield" resolves somewhere plausible on the wrong continent.
    geocode_country: str | None = Field(default="USA")

    #: How long to wait on the provider. Geocoding sits in front of a coordinator typing, so a slow
    #: answer is worse than a failed one they can retry.
    ors_timeout_seconds: float = Field(default=6.0)

    #: Browser origins allowed to call this API. The web app is deployed separately (Vercel), so
    #: every call from it is cross-origin, including in development. Production overrides this from
    #: the instance environment; the default is the `next dev` origin so a fresh checkout works.
    #: Parsed as JSON, e.g. CORS_ALLOW_ORIGINS=["https://carpool.example"].
    cors_allow_origins: list[str] = Field(default=["http://localhost:3000"])

    environment: str = Field(default="development")


@lru_cache
def get_settings() -> Settings:
    """Settings are read once per process; the cache is what makes this usable as a dependency."""
    return Settings()  # type: ignore[call-arg]  # values come from the environment
