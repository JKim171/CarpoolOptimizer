"""Application factory.

Resource routers mount under `/v1` (docs/design.md 6); the ops endpoints stay unversioned, because
load balancers and alarms should not have to track an API version.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from carpool_api.db import dispose_engine
from carpool_api.routes import ops


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="CarpoolOptimizer API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(ops.router)
    return app


app = create_app()
