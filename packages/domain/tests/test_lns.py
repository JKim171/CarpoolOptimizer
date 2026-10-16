from dataclasses import replace

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from carpool_domain import Distribution, evaluate, generate_instance, greedy, lns, validate

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


def test_a_search_stopped_at_once_returns_its_starting_point():
    instance = generate_instance(n=30, seed=5)
    start = greedy.solve(instance)
    stopped = lns.solve(instance, initial=start, should_stop=lambda: True)

    assert evaluate(instance, stopped).total == evaluate(instance, start).total


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
