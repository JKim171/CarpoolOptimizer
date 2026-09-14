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

    #: openrouteservice key. Unused until the routing adapter lands in Week 4 (docs/design.md 4.4),
    #: declared now so the deployment carries it from the start.
    ors_api_key: str | None = None

    environment: str = Field(default="development")


@lru_cache
def get_settings() -> Settings:
    """Settings are read once per process; the cache is what makes this usable as a dependency."""
    return Settings()  # type: ignore[call-arg]  # values come from the environment
