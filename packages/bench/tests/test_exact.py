import itertools
from dataclasses import replace

import pytest

from carpool_bench import exact
from carpool_domain import (
    Distribution,
    Role,
    Route,
    Solution,
    evaluate,
    generate_instance,
    greedy,
    lns,
    resequence,
    validate,
)


def _instance(n, seed, **kwargs):
    return generate_instance(n=n, seed=seed, flexible_share=0.0, **kwargs)


def _changed(instance, participant_id, **changes):
    return replace(
        instance,
        participants=tuple(
            replace(p, **changes) if p.id == participant_id else p for p in instance.participants
        ),
    )


def _brute_force(instance):
    """The optimum by trying every assignment of riders to cars, scored by `evaluate` alone."""
    drivers = [p for p in instance.participants if p.role is Role.DRIVER]
    riders = [p.id for p in instance.participants if p.role is not Role.DRIVER]
    best = float("inf")
    for choice in itertools.product([None, *range(len(drivers))], repeat=len(riders)):
        cars: list[list[str]] = [[] for _ in drivers]
        for rider, car in zip(riders, choice, strict=True):
            if car is not None:
                cars[car].append(rider)
        if any(len(group) > d.seats for d, group in zip(drivers, cars, strict=True)):
            continue
        routes = tuple(
            resequence(instance, Route(d.id, tuple(group), tuple(group)))
            for d, group in zip(drivers, cars, strict=True)
        )
        unassigned = tuple(r for r, car in zip(riders, choice, strict=True) if car is None)
        best = min(best, evaluate(instance, Solution(routes, unassigned)).total)
    return best


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_optimum_matches_trying_every_assignment(seed):
    instance = _instance(8, seed, driver_ratio=0.35)
    result = exact.solve(instance)

    assert result.optimal
    assert result.solution is not None
    assert evaluate(instance, result.solution).total == pytest.approx(_brute_force(instance))


def test_a_seat_short_event_matches_trying_every_assignment():
    # Two drivers with two seats each cannot carry six riders, so the optimum has to choose who
    # is left out.
    instance = _instance(8, 4, driver_ratio=0.25)
    for driver in [p for p in instance.participants if p.role is Role.DRIVER]:
        instance = _changed(instance, driver.id, seats=2)
    result = exact.solve(instance)

    assert result.solution is not None
    assert result.solution.unassigned
    assert evaluate(instance, result.solution).total == pytest.approx(_brute_force(instance))


@pytest.mark.parametrize("distribution", list(Distribution))
def test_the_optimum_is_feasible_and_beats_or_ties_both_heuristics(distribution):
    instance = _instance(20, 7, distribution=distribution)
    result = exact.solve(instance)

    assert result.optimal
    assert result.solution is not None
    assert validate(instance, result.solution) == []
    optimum = evaluate(instance, result.solution).total
    assert optimum == pytest.approx(result.bound, abs=1)
    assert optimum <= evaluate(instance, greedy.solve(instance)).total + 1e-6
    assert optimum <= evaluate(instance, lns.solve(instance, iterations=300)).total + 1e-6


def test_the_column_count_is_known_before_enumerating():
    instance = _instance(20, 3)
    assert exact.solve(instance).columns == exact.column_count(instance)


def test_too_many_columns_is_refused_up_front():
    instance = _instance(20, 3)
    with pytest.raises(ValueError, match="columns"):
        exact.solve(instance, max_columns=exact.column_count(instance) - 1)


def test_a_pinned_rider_rides_with_their_driver():
    instance = _instance(10, 5)
    rider = next(p for p in instance.participants if p.role is Role.PASSENGER)
    # The driver furthest from the rider: never the one an unconstrained optimum would choose.
    driver = max(
        (p for p in instance.participants if p.role is Role.DRIVER),
        key=lambda d: instance.matrix.duration(rider.id, d.id),
    )
    pinned = _changed(instance, rider.id, pinned_driver_id=driver.id)
    result = exact.solve(pinned)

    assert result.solution is not None
    assert validate(pinned, result.solution) == []
    assert result.solution.driver_of(rider.id) == driver.id


@pytest.mark.parametrize("leg", ["needs_outbound", "needs_return"])
def test_a_rider_needing_one_leg_is_carried_on_that_leg_only(leg):
    instance = _instance(10, 6)
    rider = next(p for p in instance.participants if p.role is Role.PASSENGER)
    one_way = _changed(instance, rider.id, **{leg: False})
    result = exact.solve(one_way)

    assert result.solution is not None
    assert validate(one_way, result.solution) == []
    route = next(r for r in result.solution.routes if rider.id in r.passengers)
    assert (rider.id in route.outbound) == (leg != "needs_outbound")
    assert (rider.id in route.inbound) == (leg != "needs_return")


def test_a_hint_does_not_change_the_optimum():
    instance = _instance(20, 8)
    plain = exact.solve(instance)
    hinted = exact.solve(instance, hint=greedy.solve(instance))

    assert plain.solution is not None
    assert hinted.solution is not None
    assert evaluate(instance, hinted.solution).total == pytest.approx(
        evaluate(instance, plain.solution).total
    )


@pytest.mark.parametrize(
    ("role", "changes", "message"),
    [
        (Role.PASSENGER, {"role": Role.EITHER, "seats": 3}, "flexible"),
        (Role.DRIVER, {"max_detour_seconds": 600}, "detour"),
        (Role.DRIVER, {"earliest_departure": 0}, "departure"),
    ],
)
def test_constraints_it_cannot_price_exactly_are_refused(role, changes, message):
    instance = _instance(10, 1)
    target = next(p for p in instance.participants if p.role is role)
    with pytest.raises(ValueError, match=message):
        exact.solve(_changed(instance, target.id, **changes))
