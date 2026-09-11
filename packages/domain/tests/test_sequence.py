from itertools import permutations

import pytest

from carpool_domain import (
    DESTINATION,
    Distribution,
    Location,
    ObjectiveWeights,
    Participant,
    ProblemInstance,
    Role,
    Route,
    TravelMatrix,
    generate_instance,
    resequence,
    route_metrics,
    sequence_inbound,
    sequence_outbound,
)


def cost(instance, route):
    """Score a route the way the objective does, so the DP is checked against the real target."""
    m = route_metrics(instance, route)
    w = instance.weights
    return (
        w.drive_time * (m.outbound_seconds + m.inbound_seconds)
        + w.passenger_ride_time * m.passenger_ride_seconds
        + w.driver_detour * m.detour_seconds
    )


def small_instance(seed, weights=None):
    return generate_instance(
        n=8, driver_ratio=0.2, distribution=Distribution.UNIFORM, seed=seed, weights=weights
    )


@pytest.mark.parametrize("seed", range(6))
def test_outbound_matches_exhaustive_search(seed):
    instance = small_instance(seed)
    driver, *riders = [p.id for p in instance.participants][:6]

    best = min(
        (Route(driver, outbound=order) for order in permutations(riders)),
        key=lambda r: cost(instance, r),
    )
    found = Route(driver, outbound=sequence_outbound(instance, driver, riders))

    assert cost(instance, found) == pytest.approx(cost(instance, best))


@pytest.mark.parametrize("seed", range(6))
def test_inbound_matches_exhaustive_search(seed):
    instance = small_instance(seed)
    driver, *riders = [p.id for p in instance.participants][:6]

    best = min(
        (Route(driver, inbound=order) for order in permutations(riders)),
        key=lambda r: cost(instance, r),
    )
    found = Route(driver, inbound=sequence_inbound(instance, driver, riders))

    assert cost(instance, found) == pytest.approx(cost(instance, best))


@pytest.mark.parametrize("ride_weight", [0.0, 5.0, 40.0])
def test_reversing_the_trip_out_is_optimal_when_travel_times_are_symmetric(ride_weight):
    # Not an approximation -- an identity. With edges e0..e3 and occupancy 0,1,2,3 outbound, the
    # ride-time sum is 1*e1 + 2*e2 + 3*e3; reversed, occupancy runs 3,2,1,0 over the same edges in
    # the opposite order and sums to exactly the same thing. Drive time is symmetric too, so no
    # ride weight can pull the two apart.
    instance = small_instance(3, weights=ObjectiveWeights(passenger_ride_time=ride_weight))
    driver, *riders = [p.id for p in instance.participants][:5]

    reversed_outbound = tuple(reversed(sequence_outbound(instance, driver, riders)))
    optimal_inbound = sequence_inbound(instance, driver, riders)

    assert cost(instance, Route(driver, inbound=reversed_outbound)) == pytest.approx(
        cost(instance, Route(driver, inbound=optimal_inbound))
    )


def test_asymmetric_travel_times_break_the_reversal():
    # Which is why the return leg is sequenced independently: real road networks have one-way
    # streets and turn restrictions, so a routing matrix is not symmetric (docs/design.md 8.2).
    fast, slow, far = 10, 1000, 100
    durations = {}
    for a in ("D", "x", "y", DESTINATION):
        for b in ("D", "x", "y", DESTINATION):
            if a != b:
                durations[(a, b)] = far
    durations[("x", "y")] = fast
    durations[("y", "x")] = slow  # a one-way street

    instance = ProblemInstance(
        destination=Location(0.0, 0.0),
        arrival_by=0,
        ends_at=1,
        participants=(
            Participant("D", Location(0.0, 0.0), role=Role.DRIVER, seats=2),
            Participant("x", Location(0.0, 0.0)),
            Participant("y", Location(0.0, 0.0)),
        ),
        matrix=TravelMatrix(durations),
    )

    outbound = sequence_outbound(instance, "D", ["x", "y"])
    inbound = sequence_inbound(instance, "D", ["x", "y"])

    assert outbound == ("x", "y")  # D -> x -> y -> venue avoids the slow direction
    assert inbound == ("x", "y")  # so does the return, which is therefore not the reverse
    assert inbound != tuple(reversed(outbound))


def test_resequencing_never_worsens_a_route():
    instance = small_instance(1)
    driver, *riders = [p.id for p in instance.participants][:6]
    arbitrary = Route(driver, outbound=tuple(riders), inbound=tuple(riders))

    assert cost(instance, resequence(instance, arbitrary)) <= cost(instance, arbitrary)


def test_trivial_routes_need_no_ordering():
    instance = small_instance(0)
    driver = instance.participants[0].id
    assert sequence_outbound(instance, driver, []) == ()
    assert sequence_outbound(instance, driver, ["p0007"]) == ("p0007",)
