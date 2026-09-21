"""Per-client rate limits (review H2, docs/design.md 2.4).

Anyone can create an event, and the geocoding quota is one pool shared by every user, so without
limits one script can fill the disk, drain the CPU credits, or spend the day's quota for everyone.

**In the API rather than at Caddy.** Stock Caddy has no rate limiter -- it needs a third-party
plugin compiled into a custom build -- and the per-event solve limit needs to know which event a
request is for, which only the application does. Here the limits are also tested like any other
behaviour.

**In memory, which is correct only because production runs one API process** on one instance. A
restart forgets every counter; that forgives an abuser a few minutes and costs nothing else. A
second process would give every client a second allowance, so scaling out means moving these
counters to Postgres first.

**Keyed by `request.client.host`, which is only the real client behind Caddy if uvicorn is told to
trust Caddy's `X-Forwarded-For`** (`--proxy-headers --forwarded-allow-ips=<caddy>`). Trusting it
from anyone else would let every caller claim a fresh address; not trusting it at all would put
every user behind one shared allowance.

Per-IP limits bound one client, not many. A caller with many addresses can still spend the shared
quota; the answer to that is accounts, which is a later launch gate, and haversine is the fallback
when the quota runs out.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

#: Concurrent solves across the process. The instance has two vCPUs; a burst beyond that queues and
#: gets slower instead of every solve competing for the same cores (docs/design.md 4.2).
SOLVE_CONCURRENCY = 2

#: How many hits between sweeps of fully refilled buckets, which bounds memory by recent clients.
_SWEEP_EVERY = 1024


@dataclass(frozen=True, slots=True)
class Rule:
    """`limit` units per `period` seconds, refilled continuously rather than reset on a boundary.

    A token bucket rather than a fixed window: a fixed window lets a client spend two windows' worth
    across the boundary, and a bucket needs two numbers per client where a sliding log needs one per
    request.
    """

    name: str
    limit: int
    period: float
    #: What the caller is told, completed by how long to wait.
    message: str


#: Each event mints an organizer token good for 50 participants and repeated solves, so this is the
#: limit that bounds disk growth. A coordinator creates a handful of events a week.
CREATE_EVENT = Rule("create_event", 10, 3600, "Too many events created from this network")

#: Counted in provider lookups, not requests: a pasted roster is one request and up to fifty
#: lookups, and a cache hit costs nothing. 300 is about six full rosters, a tenth of the 3,000/day
#: quota for any one client.
GEOCODE_LOOKUPS = Rule("geocode", 300, 86_400, "Daily address lookup limit reached")

#: The web app debounces the type-ahead, so a person typing stays well under this.
AUTOCOMPLETE = Rule("autocomplete", 60, 60, "Too many address suggestions requested")

#: Per event. Each solve adds a solution to the event's history, so this bounds what one organizer
#: token can write (docs/design.md 2.4).
SOLVES = Rule("solve", 20, 3600, "Too many optimizations for this event")

#: A backstop for everything under /v1, so no endpoint is unbounded by omission.
GENERAL = Rule("general", 120, 60, "Too many requests")


class RateLimited(Exception):
    def __init__(self, rule: Rule, retry_after: float) -> None:
        self.rule = rule
        self.retry_after = max(1, math.ceil(retry_after))
        super().__init__(f"{rule.message}; try again in {_wait(self.retry_after)}.")


def _wait(seconds: int) -> str:
    if seconds < 90:
        amount, unit = seconds, "second"
    elif seconds < 90 * 60:
        amount, unit = math.ceil(seconds / 60), "minute"
    else:
        amount, unit = math.ceil(seconds / 3600), "hour"
    return f"{amount} {unit}" if amount == 1 else f"{amount} {unit}s"


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        # (rule name, key) -> (the rule, tokens left, when that was computed)
        self._buckets: dict[tuple[str, str], tuple[Rule, float, float]] = {}
        self._hits = 0

    def hit(self, rule: Rule, key: str, cost: int = 1) -> None:
        """Spend `cost` units, or raise `RateLimited` having spent nothing.

        All or nothing, so a geocoding batch too large for what is left is refused whole rather
        than half-resolved -- a half-spent batch would use quota and still fail the paste.
        """
        now = self._clock()
        rate = rule.limit / rule.period
        _, tokens, then = self._buckets.get((rule.name, key), (rule, float(rule.limit), now))
        tokens = min(float(rule.limit), tokens + (now - then) * rate)
        if cost > tokens:
            raise RateLimited(rule, (cost - tokens) / rate)
        self._buckets[(rule.name, key)] = (rule, tokens - cost, now)

        self._hits += 1
        if self._hits % _SWEEP_EVERY == 0:
            self._sweep(now)

    def _sweep(self, now: float) -> None:
        """Forget buckets that have refilled: a full bucket is the same as no bucket."""
        for bucket, (rule, tokens, then) in list(self._buckets.items()):
            if tokens + (now - then) * rule.limit / rule.period >= rule.limit:
                del self._buckets[bucket]


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def get_solve_slots(request: Request) -> asyncio.Semaphore:
    """Per app rather than per module: a semaphore binds to the event loop it first waits on."""
    slots: asyncio.Semaphore = request.app.state.solve_slots
    return slots


Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]
SolveSlots = Annotated[asyncio.Semaphore, Depends(get_solve_slots)]


def limit(rule: Rule) -> Callable[[Request, RateLimiter], None]:
    """A route dependency charging one unit of `rule` to the calling client."""

    def dependency(request: Request, limiter: Limiter) -> None:
        limiter.hit(rule, client_key(request))

    return dependency


def too_many_requests(exc: RateLimited) -> JSONResponse:
    """429 with `Retry-After`. The wait is in the message too, because a cross-origin browser
    cannot read the header unless CORS exposes it, and the message is what the UI shows."""
    return JSONResponse(
        status_code=429,
        content={"detail": str(exc)},
        headers={"Retry-After": str(exc.retry_after)},
    )
