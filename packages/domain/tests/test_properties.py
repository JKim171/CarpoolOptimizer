"""Feasibility under fuzzing.

Solvers are allowed to return mediocre answers; they are never allowed to return illegal ones.
These tests assert that across arbitrary instances -- any size, any driver mix, any spatial shape,
with and without detour caps -- greedy's output always satisfies every constraint.
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from carpool_domain import Distribution, evaluate, generate_instance, greedy, validate

instances = st.builds(
    generate_instance,
    n=st.integers(min_value=2, max_value=30),
    driver_ratio=st.floats(min_value=0.05, max_value=0.9),
    distribution=st.sampled_from(list(Distribution)),
    seed=st.integers(min_value=0, max_value=10_000),
    radius_km=st.floats(min_value=0.5, max_value=30.0),
    max_detour_seconds=st.one_of(st.none(), st.integers(min_value=0, max_value=3600)),
)

slow = settings(deadline=None, max_examples=60, suppress_health_check=[HealthCheck.too_slow])


@slow
@given(instances)
def test_greedy_always_returns_a_feasible_solution(instance):
    assert validate(instance, greedy.solve(instance)) == []


@slow
@given(instances)
def test_everyone_is_either_routed_or_explicitly_unassigned(instance):
    solution = greedy.solve(instance)

    accounted = set(solution.unassigned)
    for route in solution.routes:
        accounted.add(route.driver_id)
        accounted |= route.passengers

    needs_transport = {p.id for p in instance.participants if p.needs_outbound or p.needs_return}
    assert needs_transport <= accounted


@slow
@given(instances)
def test_no_car_carries_more_people_than_it_has_seats(instance):
    for route in greedy.solve(instance).routes:
        seats = instance.participant(route.driver_id).seats
        assert len(route.outbound) <= seats
        assert len(route.inbound) <= seats


@slow
@given(instances)
def test_the_objective_is_finite_and_non_negative(instance):
    breakdown = evaluate(instance, greedy.solve(instance))

    assert breakdown.total >= 0
    assert breakdown.drive_seconds >= 0
    assert breakdown.vehicles == len(greedy.solve(instance).routes)
