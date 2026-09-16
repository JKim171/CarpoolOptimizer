"""Application factory.

Resource routers mount under `/v1` (docs/design.md 6); the ops endpoints stay unversioned, because
load balancers and alarms should not have to track an API version.
"""

from __future__ import annotations

import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from carpool_api.db import dispose_engine
from carpool_api.routes import events, ops, optimizations, participants, solutions


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def _json_safe(value: Any) -> Any:
    """Replace non-finite floats with their text form, recursively.

    `json.loads` accepts the non-standard `Infinity`, `-Infinity` and `NaN` tokens, but
    `json.dumps` refuses to emit them. A validation error echoes the offending input back to the
    caller, so rejecting `Infinity` is only half the fix: without this, the 422 *body* is what
    fails to serialize, and a bad request still ends as a 500. Rejecting the value and being able
    to say so are two different problems.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    """FastAPI's default handler, with the payload made serializable first."""
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": _json_safe(jsonable_encoder(exc.errors()))},
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="CarpoolOptimizer API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.include_router(ops.router)
    app.include_router(events.router)
    app.include_router(participants.router)
    app.include_router(optimizations.router)
    app.include_router(solutions.router)
    return app


app = create_app()
