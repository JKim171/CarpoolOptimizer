"""Operational endpoints (docs/design.md 6, "Ops").

`/healthz` and `/readyz` answer deliberately different questions:

* **healthz** -- is this process alive? It touches nothing external and must keep answering 200
  while the database is down. It is what a container restart policy and the EC2 status-check alarm
  read, and restarting the API cannot fix a database outage.
* **readyz** -- should this process receive traffic? It round-trips the database, so it fails when
  Postgres is unreachable.

Conflating the two turns a brief database blip into a restart loop.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from carpool_api.db import get_session

router = APIRouter(tags=["ops"])


class Health(BaseModel):
    status: Literal["ok"]


class Readiness(BaseModel):
    status: Literal["ready", "degraded"]
    database: Literal["up", "down"]


@router.get("/healthz", response_model=Health)
async def healthz() -> Health:
    return Health(status="ok")


@router.get("/readyz", response_model=Readiness)
async def readyz(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Readiness:
    try:
        await session.execute(text("select 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Readiness(status="degraded", database="down")
    return Readiness(status="ready", database="up")
