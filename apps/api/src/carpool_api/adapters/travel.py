"""Travel durations and distances for a set of nodes (docs/design.md 4.4).

The domain needs **durations** only -- the objective is measured in seconds, and a `TravelMatrix` is
all a solver ever asks for. Persistence needs **distances** too, because `routes.total_distance_m`
is what a results screen shows a driver. Those come from the same source and must describe the same
roads, so they are fetched and carried together rather than derived independently.

`haversine_estimates` is the provider of last resort, and Week 2's only one: straight-line distance
inflated by a road factor. It is honest about being an estimate and it needs no network, no key and
no quota, which is what makes the endpoints testable before the routing adapter exists. Week 4
replaces it with openrouteservice, whose matrix response already carries both tables -- the reason
this shape is a pair rather than a matrix.

Durations come from `carpool_domain.haversine_matrix` rather than being recomputed here: the solver
and `validate` must agree to the second about what a route costs, and two implementations of the
same formula eventually will not.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise

from carpool_domain import Location, NodeId, TravelMatrix, haversine_matrix, haversine_meters

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
