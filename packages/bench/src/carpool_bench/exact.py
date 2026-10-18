"""The exact model: set partitioning on CP-SAT (docs/design.md 8.3).

A measuring instrument, never a product feature. It exists so the heuristics' answers can be
compared against a proven optimum rather than against each other.

The model enumerates every car that could exist: each driver paired with every set of riders that
fits in their seats. Route sequencing is exact and independent of everything outside the car
(docs/design.md 8.2), so a car's cost is a constant computed up front by the same Held-Karp
sequencer the solvers use, and choosing an assignment becomes picking exactly one car per driver
such that every rider is in exactly one car or left unassigned. That is a set-partitioning problem,
whose linear relaxation is tight enough for CP-SAT to close the 50-person cap in seconds -- an
arc-based routing model, which has to rediscover sequencing inside the search, cannot.

Because both sides price a car with the same sequencer, the gap this measures is purely the
heuristics' assignment quality, which is the only thing they compete on.

The enumeration is exact only while a car's cost and feasibility depend on nothing but who is in
it. Detour caps and earliest-departure windows break that -- the cheapest ordering may violate
one where a dearer ordering would not -- so instances carrying them are refused rather than
answered approximately. So are flexible drivers (`Role.EITHER`), which production does not offer
(docs/design.md 2.3) and which this model does not price.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from ortools.sat.python import cp_model

from carpool_domain import ProblemInstance, Role, Route, Solution, resequence
from carpool_domain.greedy import route_cost

#: CP-SAT takes integer costs, so each car's is scaled and rounded. A thousandth of a
#: second-equivalent per car is far below any difference between two assignments worth reporting.
SCALE = 1000

#: Enumeration stops here rather than exhausting memory, which peaks at roughly 14 GB per million
#: columns. The largest case in the benchmark grid, 50 people with a fifth of them driving, needs
#: about 740,000 and peaked at 10.6 GB.
DEFAULT_MAX_COLUMNS = 1_000_000


@dataclass(frozen=True, slots=True)
class ExactResult:
    #: The best solution found, or None when the time limit ran out before any.
    solution: Solution | None
    #: Whether CP-SAT proved `solution` optimal.
    optimal: bool
    #: Lower bound on the objective of any solution. Equal to the optimum when `optimal`.
    bound: float
    #: Cars the model chose between.
    columns: int


def _check_supported(instance: ProblemInstance) -> None:
    for p in instance.participants:
        if p.role is Role.EITHER:
            raise ValueError(f"participant {p.id!r}: flexible drivers are not modelled")
        if p.role is Role.DRIVER and p.max_detour_seconds is not None:
            raise ValueError(f"participant {p.id!r}: detour caps are not modelled")
        if p.earliest_departure is not None:
            raise ValueError(f"participant {p.id!r}: departure windows are not modelled")


def column_count(instance: ProblemInstance) -> int:
    """How many cars the model would enumerate, computed without enumerating them."""
    riders = [
        p
        for p in instance.participants
        if p.role is not Role.DRIVER and (p.needs_outbound or p.needs_return)
    ]
    total = 0
    for driver in instance.participants:
        if driver.role is not Role.DRIVER:
            continue
        eligible = sum(1 for r in riders if r.pinned_driver_id in (None, driver.id))
        total += sum(math.comb(eligible, k) for k in range(min(driver.seats, eligible) + 1))
    return total


def _car(instance: ProblemInstance, driver: str, riders: tuple[str, ...]) -> Route:
    outbound = tuple(r for r in riders if instance.participant(r).needs_outbound)
    inbound = tuple(r for r in riders if instance.participant(r).needs_return)
    return resequence(instance, Route(driver, outbound, inbound))


def solve(
    instance: ProblemInstance,
    *,
    time_limit_seconds: float = 120.0,
    workers: int = 8,
    hint: Solution | None = None,
    max_columns: int = DEFAULT_MAX_COLUMNS,
) -> ExactResult:
    """Solve `instance` to proven optimality, or as close as `time_limit_seconds` allows.

    `hint` -- typically a heuristic's answer -- gives the search a feasible starting point, which
    matters only when the limit is tight; it never changes what is optimal.
    """
    _check_supported(instance)
    count = column_count(instance)
    if count > max_columns:
        raise ValueError(f"instance needs {count} columns, over the limit of {max_columns}")

    weights = instance.weights
    drivers = [p.id for p in instance.participants if p.role is Role.DRIVER]
    riders = [
        p.id
        for p in instance.participants
        if p.role is not Role.DRIVER and (p.needs_outbound or p.needs_return)
    ]

    model = cp_model.CpModel()
    columns: list[tuple[str, tuple[str, ...]]] = []
    chosen: list[cp_model.IntVar] = []
    costs: list[int] = []
    by_driver: dict[str, list[cp_model.IntVar]] = {d: [] for d in drivers}
    by_rider: dict[str, list[cp_model.IntVar]] = {r: [] for r in riders}

    for driver in drivers:
        seats = instance.participant(driver).seats
        eligible = [r for r in riders if instance.participant(r).pinned_driver_id in (None, driver)]
        for size in range(min(seats, len(eligible)) + 1):
            for group in itertools.combinations(eligible, size):
                var = model.new_bool_var(f"car{len(columns)}")
                columns.append((driver, group))
                chosen.append(var)
                costs.append(round(SCALE * (route_cost(instance, _car(instance, driver, group)))))
                by_driver[driver].append(var)
                for rider in group:
                    by_rider[rider].append(var)

    # Every driver drives, even alone: a fixed driver's car is part of the event whether or not
    # anyone rides in it, which is also how the solvers and the objective count it.
    for options in by_driver.values():
        model.add_exactly_one(options)

    left_out = {r: model.new_bool_var(f"unassigned_{r}") for r in riders}
    for rider, options in by_rider.items():
        model.add_exactly_one([*options, left_out[rider]])

    vehicle = round(SCALE * weights.vehicle)
    penalty = {
        r: round(SCALE * weights.unassigned * (1 + instance.participant(r).priority))
        for r in riders
    }
    model.minimize(
        cp_model.LinearExpr.weighted_sum(chosen, [c + vehicle for c in costs])
        + cp_model.LinearExpr.weighted_sum(
            [left_out[r] for r in riders], [penalty[r] for r in riders]
        )
    )

    if hint is not None:
        hinted = {(route.driver_id, route.passengers) for route in hint.routes}
        for (driver, group), var in zip(columns, chosen, strict=True):
            model.add_hint(var, (driver, frozenset(group)) in hinted)
        for rider, var in left_out.items():
            model.add_hint(var, rider in hint.unassigned)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_workers = workers
    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ExactResult(None, False, solver.best_objective_bound / SCALE, len(columns))

    routes = [
        _car(instance, driver, group)
        for (driver, group), var in zip(columns, chosen, strict=True)
        if solver.boolean_value(var)
    ]
    solution = Solution(
        routes=tuple(sorted(routes, key=lambda r: r.driver_id)),
        unassigned=tuple(sorted(r for r, var in left_out.items() if solver.boolean_value(var))),
    )
    return ExactResult(
        solution=solution,
        optimal=status == cp_model.OPTIMAL,
        bound=solver.best_objective_bound / SCALE,
        columns=len(columns),
    )
