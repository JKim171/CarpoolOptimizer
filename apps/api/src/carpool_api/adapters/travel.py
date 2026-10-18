"""Travel durations and distances for a set of nodes (docs/design.md 4.4).

The domain needs **durations** only -- the objective is measured in seconds, and a `TravelMatrix` is
all a solver ever asks for. Persistence needs **distances** too, because `routes.total_distance_m`
is what a results screen shows a driver. Those come from the same source and must describe the same
roads, so they are fetched and carried together rather than derived independently.

`OrsMatrix` is the real provider: one openrouteservice matrix request per solve, which returns both
tables at once -- the reason this shape is a pair rather than a matrix. `haversine_estimates` is the
provider of last resort: straight-line distance inflated by a road factor. It is honest about being
an estimate and needs no network, no key and no quota, so it serves tests, the generated `/demo`
event, a deployment without a key, and any solve the provider cannot answer (docs/design.md 2.4,
4.4).
`TravelEstimates.provider` says which one produced a given answer, because a solution built on
estimates has to say so rather than pass for road times.

Durations come from `carpool_domain.haversine_matrix` rather than being recomputed here: the solver
and `validate` must agree to the second about what a route costs, and two implementations of the
same formula eventually will not.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Protocol

import httpx

from carpool_api.config import Settings
from carpool_domain import (
    DESTINATION,
    Location,
    NodeId,
    TravelMatrix,
    haversine_matrix,
    haversine_meters,
)

#: A plausible urban average. Deliberately not tuned: a fictional speed tuned to look accurate is
#: worse than an obviously rough one, and Week 4 replaces this with measured road times.
DEFAULT_SPEED_KMH = 32.0

#: Roads are not straight lines.
DEFAULT_ROAD_FACTOR = 1.3


@dataclass(frozen=True, slots=True)
class TravelEstimates:
    """Directed durations and distances over the same node set, from the same provider."""

    matrix: TravelMatrix
    _distances_m: Mapping[tuple[NodeId, NodeId], int]
    #: "ors" or "haversine". Recorded on the solution, so an answer built on estimates says so.
    provider: str = "haversine"
    #: Participants the provider could not route to or from. Neither table covers them: they are
    #: left out of the solve and reported as unassigned, rather than sending everyone else to
    #: estimates (docs/design.md 4.4).
    unroutable: frozenset[NodeId] = frozenset()
    #: Metres from each node to the road the provider snapped it to. A large one is a free sign that
    #: an address geocoded wrong (docs/design.md 7.2). Empty when the provider does not report it.
    snapped_m: Mapping[NodeId, int] = field(default_factory=dict)

    def distance_m(self, origin: NodeId, destination: NodeId) -> int:
        """Metres from `origin` to `destination`, mirroring `TravelMatrix.duration`'s contract:
        zero for a node to itself, `KeyError` for a pair the provider did not return."""
        if origin == destination:
            return 0
        try:
            return self._distances_m[(origin, destination)]
        except KeyError:
            raise KeyError(f"no travel distance for {origin!r} -> {destination!r}") from None

    def path_distance_m(self, nodes: tuple[NodeId, ...]) -> int:
        return sum(self.distance_m(a, b) for a, b in pairwise(nodes))


def haversine_estimates(
    nodes: Mapping[NodeId, Location],
    *,
    speed_kmh: float = DEFAULT_SPEED_KMH,
    road_factor: float = DEFAULT_ROAD_FACTOR,
) -> TravelEstimates:
    """Straight-line estimates for every ordered pair of `nodes`.

    Symmetric, unavoidably -- so the independent return-leg sequencing the design relies on
    (docs/design.md 8.2) has nothing to exploit here and reproduces the outbound order exactly. That
    is expected under this provider and is not evidence the return sequencing is broken.
    """
    return TravelEstimates(
        matrix=haversine_matrix(nodes, speed_kmh=speed_kmh, road_factor=road_factor),
        _distances_m={
            (a, b): int(haversine_meters(la, lb) * road_factor)
            for a, la in nodes.items()
            for b, lb in nodes.items()
            if a != b
        },
    )


class TravelUnavailable(Exception):
    """The provider could not answer this request. The caller falls back to estimates."""


class Travel(Protocol):
    """The routing seam: a provider of durations and distances for a node set."""

    #: The `TravelEstimates.provider` this answers with when it succeeds.
    provider: str

    async def estimates(self, nodes: Mapping[NodeId, Location]) -> TravelEstimates: ...


class Haversine:
    """`haversine_estimates` behind the same seam, for a deployment with no provider key."""

    provider = "haversine"

    async def estimates(self, nodes: Mapping[NodeId, Location]) -> TravelEstimates:
        return haversine_estimates(nodes)


# api.heigit.org puts routing under its own prefix; the bare /v2/... paths 404 there.
_MATRIX_PATH = "/openrouteservice/v2/matrix/driving-car"


def _table(payload: dict[str, object], name: str, size: int) -> list[list[float | None]]:
    """One square table out of the response, or `TravelUnavailable` if it is not one.

    A `null` cell is kept as `None`: it means the provider found no road between that pair, which
    `_unroutable` turns into people to leave out. Anything else that is not a number is a malformed
    response.
    """
    table = payload.get(name)
    if not isinstance(table, list) or len(table) != size:
        raise TravelUnavailable(f"the matrix response has no {size}x{size} {name} table")
    rows: list[list[float | None]] = []
    for row in table:
        if not isinstance(row, list) or len(row) != size:
            raise TravelUnavailable(f"the matrix response has a malformed {name} row")
        if not all(cell is None or isinstance(cell, int | float) for cell in row):
            raise TravelUnavailable(f"the matrix response has a non-numeric {name} cell")
        rows.append([None if cell is None else float(cell) for cell in row])
    return rows


def _unroutable(tables: list[list[list[float | None]]], order: list[NodeId]) -> frozenset[NodeId]:
    """Participants whose removal leaves no `null` cell, chosen greedily.

    An address the provider cannot snap to a road nulls its whole row and column, so it has by far
    the most missing cells and goes first; a pair of points with no road between them (an island)
    costs one of the two. Filling a missing cell with a straight-line number instead would mix two
    providers in one answer that claims to be road times.

    The destination is never removed -- without it there is nothing to solve -- so when it is the
    node with the most missing cells, the solve goes to estimates. So does losing more than half
    the roster: that is the provider failing, not the addresses.
    """
    missing = {
        (i, j)
        for table in tables
        for i, row in enumerate(table)
        for j, cell in enumerate(row)
        if i != j and cell is None
    }
    removed: set[int] = set()
    while missing:
        counts: dict[int, int] = {}
        for i, j in missing:
            counts[i] = counts.get(i, 0) + 1
            counts[j] = counts.get(j, 0) + 1
        # Most missing cells first. A tie goes against a participant rather than the destination,
        # then against the earlier node, so the answer is deterministic.
        worst = max(counts, key=lambda k: (counts[k], order[k] != DESTINATION, -k))
        if order[worst] == DESTINATION:
            raise TravelUnavailable("the destination could not be routed to by road")
        removed.add(worst)
        missing = {(i, j) for i, j in missing if worst not in (i, j)}
    if len(removed) * 2 > len(order) - 1:
        raise TravelUnavailable("most points could not be routed to by road")
    return frozenset(order[k] for k in removed)


def _snapped(payload: dict[str, object], order: list[NodeId]) -> dict[NodeId, int]:
    """Each node's snap distance from the response's `sources`, where it gives one.

    Advisory, so never a reason to refuse an answer: a missing or odd entry is simply not reported.
    """
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != len(order):
        return {}
    snapped: dict[NodeId, int] = {}
    for node, source in zip(order, sources, strict=True):
        distance = source.get("snapped_distance") if isinstance(source, dict) else None
        if isinstance(distance, int | float):
            snapped[node] = round(distance)
    return snapped


def parse_matrix(payload: object, order: list[NodeId]) -> TravelEstimates:
    """Read an ORS matrix response whose rows and columns follow `order`.

    Durations arrive as float seconds and distances as float metres; both are rounded to integers
    here, at the boundary, because the domain is integer seconds throughout (CLAUDE.md). The tables
    cover every node but the `unroutable` ones.
    """
    if not isinstance(payload, dict):
        raise TravelUnavailable("the matrix response is not an object")
    durations = _table(payload, "durations", len(order))
    distances = _table(payload, "distances", len(order))
    unroutable = _unroutable([durations, distances], order)
    kept = [(i, node) for i, node in enumerate(order) if node not in unroutable]
    pairs = [(i, a, j, b) for i, a in kept for j, b in kept if a != b]
    return TravelEstimates(
        matrix=TravelMatrix({(a, b): round(_cell(durations, i, j)) for i, a, j, b in pairs}),
        _distances_m={(a, b): round(_cell(distances, i, j)) for i, a, j, b in pairs},
        provider="ors",
        unroutable=unroutable,
        snapped_m={
            node: m for node, m in _snapped(payload, order).items() if node not in unroutable
        },
    )


def _cell(table: list[list[float | None]], i: int, j: int) -> float:
    cell = table[i][j]
    # `_unroutable` removed every node on a missing cell; reaching one here is a bug in it.
    assert cell is not None, f"missing cell {i},{j} survived"
    return cell


class OrsMatrix:
    """openrouteservice's matrix endpoint: every node once, both metrics, one request.

    Listing every point as a location and naming no `sources` or `destinations` returns the full
    directed square, which covers both legs -- the return reads the destination's row
    (docs/design.md 4.4). The participant cap is sized so that square fits one request
    (`carpool_api.limits`), so there is no tiling and no partial failure to handle.
    """

    provider = "ors"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    async def estimates(self, nodes: Mapping[NodeId, Location]) -> TravelEstimates:
        if not self._settings.ors_api_key:
            raise TravelUnavailable("ORS_API_KEY is not configured")
        order = list(nodes)
        # Longitude first. A swap raises nothing and routes every driver to the wrong hemisphere,
        # which is why the order is pinned by a test (docs/design.md 4.4).
        body = {
            "locations": [[nodes[node].lng, nodes[node].lat] for node in order],
            "metrics": ["duration", "distance"],
        }
        # A header rather than the `api_key` query parameter, so the key stays out of logged URLs.
        headers = {"Authorization": self._settings.ors_api_key}
        timeout = self._settings.ors_timeout_seconds
        url = f"{self._settings.ors_base_url.rstrip('/')}{_MATRIX_PATH}"
        try:
            if self._client is not None:
                response = await self._client.post(url, json=body, headers=headers, timeout=timeout)
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise TravelUnavailable(f"could not reach the routing provider: {exc}") from exc

        if response.status_code >= 400:
            # 429 included: the quota is shared and daily, and estimates are the documented answer
            # when it runs out (docs/design.md 2.4). The body is never quoted -- it can echo the
            # request, which holds everyone's coordinates.
            raise TravelUnavailable(f"the routing provider returned {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TravelUnavailable("the routing provider returned a malformed response") from exc
        return parse_matrix(payload, order)


async def estimates_or_fallback(
    travel: Travel, nodes: Mapping[NodeId, Location]
) -> TravelEstimates:
    """The provider's answer, or straight-line estimates when it has none.

    A solve on estimates is a worse answer than a solve on road times, and a better one than no
    answer an hour before practice. The result carries `provider`, so it is never mistaken for the
    real thing -- and the caller keeps it out of fingerprint reuse, so the next solve asks again.
    """
    try:
        return await travel.estimates(nodes)
    except TravelUnavailable:
        return haversine_estimates(nodes)
