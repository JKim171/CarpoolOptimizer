"""The benchmark grid (docs/design.md 8.5).

Every case is a generated instance, fixed by its seed, solved three ways: greedy alone, LNS exactly
as production runs it, and -- where the instance is small enough to enumerate -- the exact model,
which turns the first two into gaps against a proven optimum.

LNS runs on a wall-clock budget because production does, so its numbers depend on the machine and
vary a little between runs. Each record says how many iterations the budget bought, which is the
portable part. The machine is recorded with the results.

Instances are generated without flexible drivers, the shape production solves while the roster UI
does not offer the role (docs/design.md 2.3). That also means the driver set is fixed and the
`vehicles` column is decided by the instance, not by the solver.
"""

from __future__ import annotations

import platform
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

from carpool_domain import (
    Distribution,
    ProblemInstance,
    Solution,
    evaluate,
    generate_instance,
    greedy,
    lns,
    route_metrics,
    validate,
)

from . import exact

SIZES = (20, 50, 100, 250, 500, 1000)
DRIVER_RATIOS = (0.2, 0.35, 0.5)
DISTRIBUTIONS = tuple(Distribution)
SEEDS = (1, 2, 3)

#: The largest events the exact model is asked to solve. Fifty is production's cap
#: (docs/design.md 2.4), so every event a user can create is inside it.
EXACT_MAX_N = 50
EXACT_TIME_LIMIT_SECONDS = 300.0

#: The API's search budget and iteration cap (`routes/optimizations.py`). Repeated rather than
#: imported, because the harness does not depend on the API; what it measures is that configuration.
LNS_BUDGET_SECONDS = 1.0
LNS_MAX_ITERATIONS = 20_000


@dataclass(frozen=True, slots=True)
class Case:
    n: int
    driver_ratio: float
    distribution: Distribution
    seed: int

    def instance(self) -> ProblemInstance:
        return generate_instance(
            n=self.n,
            driver_ratio=self.driver_ratio,
            distribution=self.distribution,
            seed=self.seed,
            flexible_share=0.0,
        )


def grid(
    sizes: Iterable[int] = SIZES,
    driver_ratios: Iterable[float] = DRIVER_RATIOS,
    distributions: Iterable[Distribution] = DISTRIBUTIONS,
    seeds: Iterable[int] = SEEDS,
) -> list[Case]:
    return [
        Case(n, ratio, distribution, seed)
        for n in sizes
        for ratio in driver_ratios
        for distribution in distributions
        for seed in seeds
    ]


def _percentile(values: list[int], fraction: float) -> int:
    """Nearest rank, as the API computes `p95_detour_s` (`adapters/solutions.py`)."""
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def measure(instance: ProblemInstance, solution: Solution) -> dict[str, Any]:
    """The per-solution numbers design 8.5 asks for, named as the API's `metrics` names them."""
    violations = validate(instance, solution)
    if violations:
        # A benchmark of an infeasible answer measures nothing, and a solver producing one is a bug.
        raise AssertionError(f"infeasible solution: {violations[:3]}")
    breakdown = evaluate(instance, solution)
    detours = [route_metrics(instance, route).detour_seconds for route in solution.routes]
    penalty = instance.weights.unassigned * breakdown.unassigned_weight
    return {
        "objective": breakdown.total,
        # The objective less the penalty for riders left out. In a seat-short event every solver
        # pays the same penalty for the same number of riders, and gaps are measured on this so
        # that a fixed charge does not shrink them.
        "routing_cost": breakdown.total - penalty,
        "drive_s": breakdown.drive_seconds,
        "passenger_ride_s": breakdown.passenger_ride_seconds,
        "driver_detour_s": breakdown.driver_detour_seconds,
        "p95_detour_s": _percentile(detours, 0.95),
        "vehicles": breakdown.vehicles,
        "unassigned": len(solution.unassigned),
    }


def _timed[T](solve: Callable[[], T]) -> tuple[T, float]:
    began = time.perf_counter()
    result = solve()
    return result, time.perf_counter() - began


@dataclass(frozen=True, slots=True)
class Settings:
    lns_budget_seconds: float = LNS_BUDGET_SECONDS
    lns_max_iterations: int = LNS_MAX_ITERATIONS
    exact_max_n: int = EXACT_MAX_N
    exact_time_limit_seconds: float = EXACT_TIME_LIMIT_SECONDS


DEFAULT_SETTINGS = Settings()


def run_case(case: Case, settings: Settings = DEFAULT_SETTINGS) -> Iterator[dict[str, Any]]:
    """One record per solver for `case`."""
    instance = case.instance()
    common = {
        "n": case.n,
        "driver_ratio": case.driver_ratio,
        "distribution": case.distribution.value,
        "seed": case.seed,
    }

    start, seconds = _timed(lambda: greedy.solve(instance))
    yield {**common, "solver": "greedy", "seconds": seconds, **measure(instance, start)}

    # As the API runs it: greedy inside the budget, then the search for whatever is left of it.
    iterations = 0

    def production_lns() -> Solution:
        began = time.monotonic()

        def progress() -> float:
            nonlocal iterations
            iterations += 1
            return (time.monotonic() - began) / settings.lns_budget_seconds

        return lns.solve(
            instance,
            initial=greedy.solve(instance),
            iterations=settings.lns_max_iterations,
            progress=progress,
        )

    searched, seconds = _timed(production_lns)
    yield {
        **common,
        "solver": "lns",
        "seconds": seconds,
        # `progress` is read once per iteration and once more by the check that ends the search, so
        # this is exact to within one.
        "iterations": min(iterations, settings.lns_max_iterations),
        **measure(instance, searched),
    }

    if case.n > settings.exact_max_n:
        return
    result, seconds = _timed(
        lambda: exact.solve(
            instance, time_limit_seconds=settings.exact_time_limit_seconds, hint=searched
        )
    )
    record: dict[str, Any] = {
        **common,
        "solver": "exact",
        "seconds": seconds,
        "optimal": result.optimal,
        "bound": result.bound,
        "columns": result.columns,
    }
    if result.solution is not None:
        record.update(measure(instance, result.solution))
    yield record


def run(
    cases: Iterable[Case],
    settings: Settings = DEFAULT_SETTINGS,
    *,
    on_record: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Every case, with the environment the numbers came from. Runtime is comparable only within
    one environment; quality is comparable across them, except that a faster machine buys LNS more
    iterations in the same second."""
    runs = []
    for case in cases:
        for record in run_case(case, settings):
            runs.append(record)
            if on_record is not None:
                on_record(record)
    return {
        "environment": {
            "machine": platform.machine(),
            "system": platform.system(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "ortools": version("ortools"),
            "lns_budget_seconds": settings.lns_budget_seconds,
            "lns_max_iterations": settings.lns_max_iterations,
            "exact_max_n": settings.exact_max_n,
            "exact_time_limit_seconds": settings.exact_time_limit_seconds,
        },
        "runs": runs,
    }
