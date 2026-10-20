from dataclasses import replace

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from carpool_domain import (
    Distribution,
    evaluate,
    generate_instance,
    greedy,
    lns,
    validate,
)

instances = st.builds(
    generate_instance,
    n=st.integers(min_value=2, max_value=25),
    driver_ratio=st.floats(min_value=0.05, max_value=0.9),
    distribution=st.sampled_from(list(Distribution)),
    seed=st.integers(min_value=0, max_value=10_000),
    radius_km=st.floats(min_value=0.5, max_value=30.0),
    max_detour_seconds=st.one_of(st.none(), st.integers(min_value=0, max_value=3600)),
)

slow = settings(deadline=None, max_examples=40, suppress_health_check=[HealthCheck.too_slow])


@slow
@given(instances, st.integers(min_value=0, max_value=1000))
def test_lns_always_returns_a_feasible_solution(instance, seed):
    assert validate(instance, lns.solve(instance, iterations=60, seed=seed)) == []


@slow
@given(instances)
def test_lns_is_never_worse_than_where_it_started(instance):
    start = greedy.solve(instance)
    improved = lns.solve(instance, initial=start, iterations=60)

    assert evaluate(instance, improved).total <= evaluate(instance, start).total


def test_lns_improves_on_greedy_where_greedy_leaves_room():
    instance = generate_instance(n=50, seed=1, distribution=Distribution.CLUSTERED)
    start = greedy.solve(instance)
    improved = lns.solve(instance, initial=start, iterations=500)

    assert evaluate(instance, improved).total < 0.97 * evaluate(instance, start).total


def test_the_same_seed_gives_the_same_answer():
    instance = generate_instance(n=30, seed=5)
    assert lns.solve(instance, iterations=200, seed=3) == lns.solve(
        instance, iterations=200, seed=3
    )


def test_a_spent_budget_returns_the_starting_point():
    instance = generate_instance(n=30, seed=5)
    start = greedy.solve(instance)
    stopped = lns.solve(instance, initial=start, progress=lambda: 1.0)

    assert evaluate(instance, stopped).total == evaluate(instance, start).total


def test_progress_ends_the_search_before_the_iteration_cap():
    instance = generate_instance(n=30, seed=5)
    calls = 0

    def progress() -> float:
        nonlocal calls
        calls += 1
        return calls / 50

    solution = lns.solve(instance, iterations=10_000, progress=progress)

    assert calls == 50
    assert validate(instance, solution) == []


def test_pins_survive_the_search():
    base = generate_instance(n=30, seed=9)
    rider = next(p for p in base.participants if not p.role.can_drive)
    # The furthest committed driver, so the pin is one the search would gladly undo.
    driver = max(
        (p for p in base.participants if p.role.value == "driver"),
        key=lambda p: base.matrix.duration(rider.id, p.id),
    )
    pinned = replace(
        base,
        participants=tuple(
            replace(p, pinned_driver_id=driver.id) if p.id == rider.id else p
            for p in base.participants
        ),
    )
    solution = lns.solve(pinned, iterations=300)

    assert validate(pinned, solution) == []
    assert solution.driver_of(rider.id) == driver.id


# -- seat-short events: who is left out -----------------------------------------------------------


@slow
@given(
    st.builds(
        generate_instance,
        n=st.integers(min_value=4, max_value=25),
        driver_ratio=st.floats(min_value=0.05, max_value=0.25),
        distribution=st.sampled_from(list(Distribution)),
        seed=st.integers(min_value=0, max_value=10_000),
        flexible_share=st.sampled_from([0.0, 0.15]),
        max_detour_seconds=st.one_of(st.none(), st.integers(min_value=0, max_value=3600)),
    ),
    st.integers(min_value=0, max_value=1000),
)
def test_seat_short_searches_stay_feasible_and_never_lose_ground(instance, seed):
    start = greedy.solve(instance)
    solution = lns.solve(instance, initial=start, iterations=60, seed=seed)

    assert validate(instance, solution) == []
    assert evaluate(instance, solution).total <= evaluate(instance, start).total


# -- re-optimization against a previous solution (docs/design.md 8.4) ------------------------------


def _with_churn(instance, weight=300.0):
    return replace(instance, weights=replace(instance.weights, churn=weight))


def _without_people(instance, *gone):
    return replace(
        instance, participants=tuple(p for p in instance.participants if p.id not in gone)
    )


@slow
@given(instances, st.integers(min_value=0, max_value=1000), st.data())
def test_re_optimizing_after_the_roster_changes_stays_feasible(instance, seed, data):
    previous = greedy.solve(instance)
    leaving = data.draw(st.sets(st.sampled_from([p.id for p in instance.participants]), max_size=3))
    changed = _with_churn(_without_people(instance, *leaving))
    if not changed.participants:
        return

    assert validate(changed, lns.solve(changed, iterations=60, seed=seed, previous=previous)) == []


@slow
@given(instances)
def test_re_optimizing_is_never_worse_than_a_fresh_greedy_answer_with_churn_counted(instance):
    previous = lns.solve(instance, iterations=60, seed=1)
    changed = _with_churn(instance)
    fresh = greedy.solve(changed)
    again = lns.solve(changed, iterations=60, previous=previous)

    assert (
        evaluate(changed, again, previous=previous).total
        <= evaluate(changed, fresh, previous=previous).total
    )


def test_someone_leaving_moves_nobody_else_when_churn_is_dear():
    instance = generate_instance(n=40, seed=3, distribution=Distribution.CLUSTERED)
    previous = lns.solve(instance, iterations=300)
    rider = next(r for route in previous.routes for r in sorted(route.passengers))
    changed = _with_churn(_without_people(instance, rider), weight=10_000.0)

    again = lns.solve(changed, iterations=300, previous=previous)

    assert validate(changed, again) == []
    assert evaluate(changed, again, previous=previous).churn == 0


def test_churn_pricing_keeps_more_riders_in_their_cars_than_a_fresh_search():
    instance = generate_instance(n=50, seed=2, distribution=Distribution.UNIFORM)
    previous = greedy.solve(instance)
    leaving = sorted(p.id for p in instance.participants if not p.role.can_drive)[:3]
    changed = _with_churn(_without_people(instance, *leaving))

    fresh = lns.solve(changed, iterations=300)
    kept = lns.solve(changed, iterations=300, previous=previous)

    assert (
        evaluate(changed, kept, previous=previous).churn
        < evaluate(changed, fresh, previous=previous).churn
    )


def test_without_a_churn_weight_previous_changes_nothing():
    instance = generate_instance(n=30, seed=5)
    previous = greedy.solve(_without_people(instance, instance.participants[-1].id))

    assert lns.solve(
        instance, iterations=200, previous=previous, initial=greedy.solve(instance)
    ) == (lns.solve(instance, iterations=200, initial=greedy.solve(instance)))


def test_the_search_starts_from_the_previous_answer_not_from_greedy():
    instance = generate_instance(n=40, seed=3, distribution=Distribution.CLUSTERED)
    previous = lns.solve(instance, iterations=500)
    changed = _with_churn(instance)
    assert evaluate(changed, greedy.solve(changed), previous=previous).churn > 0

    # No moves at all, so what comes back is the starting point.
    start = lns.solve(changed, progress=lambda: 1.0, previous=previous)

    assert evaluate(changed, start, previous=previous).churn == 0
    assert validate(changed, start) == []
