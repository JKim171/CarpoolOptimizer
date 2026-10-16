"""Large neighbourhood search (docs/design.md 8.3).

The production algorithm. It starts from greedy's answer and repeatedly tears part of it down and
builds it back up, keeping the change when simulated annealing says to. Greedy commits to each
rider once, in a fixed order, and never revisits the choice; this is the revisiting.

Only assignment is searched. Every car a move touches is resequenced exactly (`sequence`), so the
2-opt in the design's operator list has nothing left to improve: no ordering of a passenger car
beats the Held-Karp one. Relocate is ruin-and-recreate of a single rider. Swap is its own move,
because exchanging two riders between two *full* cars is the one change insertion cannot make --
removing either rider first frees the very seat the other needs.

The budget is a number of iterations rather than seconds, because this package reads no clock
(docs/design.md 4.1). A caller that wants a wall-clock limit passes `should_stop`, consulted once
per iteration. Cooling still follows the iteration count, so a search stopped early ends warm --
which costs some quality, never feasibility. Every accepted state is feasible route by route, and
the answer returned is the best one seen, so it is never worse than the starting solution.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass

from . import greedy
from .models import DESTINATION, ProblemInstance, Role, Route, Solution
from .sequence import resequence
from .validate import route_feasible

DEFAULT_ITERATIONS = 2_000

#: Most riders a single ruin removes. Enough to rearrange a neighbourhood of several cars at once;
#: past it, rebuilding costs more than the larger move is worth.
MAX_RUIN = 30

#: The starting temperature accepts a move this much worse than the starting solution, as a
#: fraction of its cost, half the time.
START_WORSE_FRACTION = 0.05

#: Final temperature as a fraction of the starting one. Low enough that the last stretch of the
#: search is effectively a descent.
END_TEMPERATURE_RATIO = 0.005

#: Memo tables are dropped wholesale past this many entries, which bounds memory on long searches.
_CACHE_LIMIT = 200_000


@dataclass(slots=True)
class _State:
    """A solution under construction: open cars by driver, and riders nobody is carrying."""

    routes: dict[str, Route]
    unassigned: set[str]

    def copy(self) -> _State:
        return _State(dict(self.routes), set(self.unassigned))

    def placed(self) -> list[tuple[str, str]]:
        """Every seated rider with their driver, in a deterministic order."""
        return sorted(
            (rider, driver) for driver, route in self.routes.items() for rider in route.passengers
        )


def _without(route: Route, rider: str) -> Route:
    return Route(
        route.driver_id,
        tuple(p for p in route.outbound if p != rider),
        tuple(p for p in route.inbound if p != rider),
    )


class _Search:
    def __init__(self, instance: ProblemInstance, rng: random.Random, candidates: int) -> None:
        self.instance = instance
        self.rng = rng
        self.candidates = candidates
        self._costs: dict[Route, float] = {}
        self._sequenced: dict[Route, Route] = {}

        matrix = instance.matrix
        drivers = [p.id for p in instance.participants if p.role.can_drive]
        riders = [
            p.id
            for p in instance.participants
            if p.role is not Role.DRIVER and (p.needs_outbound or p.needs_return)
        ]
        # Fixed for the whole search, so sorted once: the cars nearest each rider, open or not.
        self.nearest: dict[str, tuple[str, ...]] = {
            r: tuple(
                sorted((d for d in drivers if d != r), key=lambda d: (matrix.duration(r, d), d))
            )
            for r in riders
        }

    # -- pricing -----------------------------------------------------------------------------

    def route_cost(self, instance: ProblemInstance, route: Route) -> float:
        cost = self._costs.get(route)
        if cost is None:
            if len(self._costs) > _CACHE_LIMIT:
                self._costs.clear()
            cost = self._costs[route] = greedy.route_cost(instance, route)
        return cost

    def total(self, state: _State) -> float:
        weights = self.instance.weights
        return (
            sum(self.route_cost(self.instance, r) for r in state.routes.values())
            + weights.vehicle * len(state.routes)
            + weights.unassigned
            * sum(1 + self.instance.participant(p).priority for p in state.unassigned)
        )

    def tidy(self, route: Route) -> Route:
        """`route` optimally ordered, or as it was when the optimal order breaks a detour cap."""
        tidied = self._sequenced.get(route)
        if tidied is None:
            if len(self._sequenced) > _CACHE_LIMIT:
                self._sequenced.clear()
            resequenced = resequence(self.instance, route)
            tidied = resequenced if route_feasible(self.instance, resequenced) else route
            self._sequenced[route] = tidied
        return tidied

    # -- moves -------------------------------------------------------------------------------

    def ruin(self, state: _State) -> set[str] | None:
        """Remove some riders from their cars in place, returning who, or None if nobody can be."""
        placed = state.placed()
        closable = sorted(
            d
            for d, route in state.routes.items()
            if route.passengers or self.instance.participant(d).role is not Role.DRIVER
        )
        if not placed and not closable:
            return None
        k = self.rng.randint(1, max(1, min(MAX_RUIN, len(placed) // 4)))
        operator = self.rng.random()

        removed: set[str]
        if operator < 0.2 and closable:
            # Empty one car. A flexible driver loses the car too and goes back into the pool as a
            # rider, which is the only way the search can ever use fewer cars than it started with.
            driver = self.rng.choice(closable)
            removed = set(state.routes[driver].passengers)
            if self.instance.participant(driver).role is not Role.DRIVER:
                del state.routes[driver]
                removed.add(driver)
            else:
                state.routes[driver] = Route(driver)
            return removed
        if not placed:
            return None
        if operator < 0.6:
            removed = {rider for rider, _ in self.rng.sample(placed, k)}
        else:
            # Neighbours of one rider, so the rebuild can regroup a whole area rather than a
            # scattering of unrelated seats.
            matrix = self.instance.matrix
            seed, _ = self.rng.choice(placed)
            nearest = sorted(
                placed,
                key=lambda pair: (
                    matrix.duration(seed, pair[0]) + matrix.duration(pair[0], seed),
                    pair[0],
                ),
            )
            removed = {rider for rider, _ in nearest[:k]}

        for rider, driver in placed:
            if rider in removed:
                state.routes[driver] = _without(state.routes[driver], rider)
        return removed

    def recreate(self, state: _State, pending: set[str]) -> None:
        """Seat everyone in `pending` and every already-unassigned rider, cheapest place first."""
        instance = self.instance
        pool = pending | state.unassigned
        state.unassigned = set()

        # Pins first, as in greedy: they are constraints, and must claim their seat before anyone
        # else can spend it.
        pinned = sorted(p for p in pool if instance.participant(p).pinned_driver_id is not None)
        for rider in pinned:
            pool.discard(rider)
            target = instance.participant(rider).pinned_driver_id
            assert target is not None
            if target not in state.routes and target in pool:
                state.routes[target] = Route(target)
                pool.discard(target)
            route = state.routes.get(target)
            insertion = (
                greedy.best_insertion(instance, route, rider, cost=self.route_cost)
                if route is not None
                else None
            )
            if insertion is None:
                state.unassigned.add(rider)
            else:
                state.routes[target] = insertion[0]

        # The order riders are rebuilt in is itself randomized: furthest-first is greedy's choice
        # and usually right, but not always, and the search is only as varied as its rebuilds.
        order = sorted(pool)
        matrix_to_venue = {r: instance.matrix.duration(r, DESTINATION) for r in order}
        style = self.rng.random()
        if style < 0.5:
            order.sort(key=lambda r: -matrix_to_venue[r])
        elif style < 0.75:
            self.rng.shuffle(order)
        else:
            order.sort(key=lambda r: matrix_to_venue[r])

        for rider in order:
            if rider not in pool:
                # Opened a car of their own earlier in this rebuild, for a pinned passenger.
                continue
            self._seat(state, rider)

    def _seat(self, state: _State, rider: str) -> None:
        instance = self.instance
        best: tuple[str, Route, float] | None = None
        seen = 0
        for driver in self.nearest[rider]:
            route = state.routes.get(driver)
            if route is None:
                continue
            seen += 1
            insertion = greedy.best_insertion(instance, route, rider, cost=self.route_cost)
            if insertion is not None and (best is None or insertion[1] < best[2]):
                best = (driver, insertion[0], insertion[1])
            if seen >= self.candidates:
                break

        participant = instance.participant(rider)
        solo = Route(rider)
        if participant.role.can_drive and route_feasible(instance, solo):
            solo_cost = instance.weights.vehicle + self.route_cost(instance, solo)
            if best is None or best[2] > solo_cost:
                state.routes[rider] = solo
                return
        if best is None:
            state.unassigned.add(rider)
        else:
            state.routes[best[0]] = best[1]

    def swap(self, state: _State) -> set[str] | None:
        """Exchange two riders between two cars in place, returning the drivers touched."""
        placed = state.placed()
        if len(placed) < 2:
            return None
        (a, car_a), (b, car_b) = self.rng.sample(placed, 2)
        if car_a == car_b:
            return None
        pins = {self.instance.participant(r).pinned_driver_id for r in (a, b)}
        if pins - {None}:
            return None
        into_b = greedy.best_insertion(
            self.instance, _without(state.routes[car_b], b), a, cost=self.route_cost
        )
        into_a = greedy.best_insertion(
            self.instance, _without(state.routes[car_a], a), b, cost=self.route_cost
        )
        if into_a is None or into_b is None:
            return None
        state.routes[car_a], state.routes[car_b] = into_a[0], into_b[0]
        return {car_a, car_b}


def solve(
    instance: ProblemInstance,
    *,
    initial: Solution | None = None,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 0,
    should_stop: Callable[[], bool] | None = None,
    candidate_drivers: int = greedy.DEFAULT_CANDIDATE_DRIVERS,
) -> Solution:
    """Improve on `initial` (greedy's answer by default) for up to `iterations` moves.

    `initial` must be feasible; it is the floor on quality, since the best solution seen is what
    comes back. The same instance, initial solution and seed always give the same answer.
    """
    start = initial if initial is not None else greedy.solve(instance)
    rng = random.Random(seed)
    search = _Search(instance, rng, candidate_drivers)

    current = _State({r.driver_id: r for r in start.routes}, set(start.unassigned))
    current_cost = search.total(current)
    best, best_cost = current.copy(), current_cost

    # Temperature is scaled to the cost of driving, not to the unassigned penalty: one stranded
    # rider outweighs any amount of driving, and a temperature that large would accept anything.
    driving = current_cost - instance.weights.unassigned * sum(
        1 + instance.participant(p).priority for p in current.unassigned
    )
    start_temperature = max(1.0, START_WORSE_FRACTION * driving / math.log(2))

    for iteration in range(iterations):
        if should_stop is not None and should_stop():
            break
        temperature = start_temperature * END_TEMPERATURE_RATIO ** (iteration / iterations)

        candidate = current.copy()
        before = dict(candidate.routes)
        if rng.random() < 0.15:
            if search.swap(candidate) is None:
                continue
        else:
            removed = search.ruin(candidate)
            if removed is None:
                continue
            search.recreate(candidate, removed)

        # Only the cars that changed need tidying and rechecking. The recheck is not redundant:
        # insertion only ever adds feasible stops, but taking a stop out can lengthen a route on
        # a real road matrix, where the triangle inequality does not hold.
        feasible = True
        for driver, route in candidate.routes.items():
            if before.get(driver) == route:
                continue
            tidied = search.tidy(route)
            if not route_feasible(instance, tidied):
                feasible = False
                break
            candidate.routes[driver] = tidied
        if not feasible:
            continue

        cost = search.total(candidate)
        delta = cost - current_cost
        if delta < 0 or rng.random() < math.exp(-delta / temperature):
            current, current_cost = candidate, cost
            if cost < best_cost - 1e-9:
                best, best_cost = candidate.copy(), cost

    return Solution(
        routes=tuple(best.routes[d] for d in sorted(best.routes)),
        unassigned=tuple(sorted(best.unassigned)),
    )
