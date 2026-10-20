from dataclasses import replace

from carpool_domain import (
    DESTINATION,
    Distribution,
    Location,
    Participant,
    ProblemInstance,
    Role,
    Route,
    generate_instance,
    greedy,
    haversine_matrix,
    validate,
)


def test_everyone_is_seated_when_there_is_room(instance):
    solution = greedy.solve(instance)

    assert validate(instance, solution) == []
    assert solution.unassigned == ()
    assert {r.driver_id for r in solution.routes} == {"d"}
    assert set(solution.routes[0].passengers) == {"a", "b"}


def test_riders_who_do_not_fit_are_reported_not_dropped(instance):
    one_seat = replace(
        instance,
        participants=(
            replace(instance.participant("d"), seats=1),
            instance.participant("a"),
            instance.participant("b"),
        ),
    )
    solution = greedy.solve(one_seat)

    assert validate(one_seat, solution) == []
    assert len(solution.unassigned) == 1


def test_pins_are_honoured(instance):
    pinned = replace(
        instance,
        participants=(
            replace(instance.participant("d"), seats=1),
            # 'a' is nearer the venue, so unpinned greed would seat 'b' first.
            replace(instance.participant("a"), pinned_driver_id="d"),
            instance.participant("b"),
        ),
    )
    solution = greedy.solve(pinned)

    assert validate(pinned, solution) == []
    assert "a" in solution.routes[0].passengers
    assert solution.unassigned == ("b",)


def test_with_no_drivers_nobody_is_stranded_silently(instance):
    driverless = replace(
        instance,
        participants=tuple(replace(p, role=Role.PASSENGER, seats=0) for p in instance.participants),
    )
    solution = greedy.solve(driverless)

    assert solution.routes == ()
    assert set(solution.unassigned) == {"d", "a", "b"}
    assert validate(driverless, solution) == []


def test_a_flexible_rider_will_drive_rather_than_be_stranded():
    instance = generate_instance(n=12, driver_ratio=0.1, seed=4, distribution=Distribution.RADIAL)
    solution = greedy.solve(instance)

    # driver_ratio 0.1 of 12 is one committed driver; flexible riders must open the other cars.
    assert len(solution.routes) > 1
    assert validate(instance, solution) == []


def test_solving_is_deterministic():
    instance = generate_instance(n=40, seed=7)
    assert greedy.solve(instance) == greedy.solve(instance)


def test_a_full_car_is_refused_before_any_position_is_priced(instance):
    full = replace(instance.participant("d"), seats=1)
    one_seat = replace(instance, participants=(full, *instance.participants[1:]))

    def unpriceable(_instance, _route):
        raise AssertionError("priced a car with no seat left")

    car = Route("d", ("a",), ("a",))
    assert greedy.best_insertion(one_seat, car, "b", cost=unpriceable) is None


def test_a_flexible_rider_driving_for_a_pin_is_not_seated_again(instance):
    # 'b' is pinned to flexible 'a', so 'a' drives -- and must not also be placed as a rider.
    pinned = replace(
        instance,
        participants=(
            instance.participant("d"),
            replace(instance.participant("a"), role=Role.EITHER, seats=2),
            replace(instance.participant("b"), pinned_driver_id="a"),
        ),
    )
    solution = greedy.solve(pinned)

    assert validate(pinned, solution) == []
    assert solution.driver_of("b") == "a"


def _one_seat_two_riders():
    """One seat, two riders: `near` sits on the driver's way in, `far` is miles the other way."""
    venue = Location(43.07, -89.40)
    people = (
        Participant("d", Location(43.115, -89.40), role=Role.DRIVER, seats=1),
        Participant("near", Location(43.0925, -89.40)),
        Participant("far", Location(43.0, -89.40)),
    )
    nodes = {p.id: p.location for p in people} | {DESTINATION: venue}
    return ProblemInstance(
        destination=venue,
        arrival_by=1_000_000,
        ends_at=1_007_200,
        participants=people,
        matrix=haversine_matrix(nodes),
    )


def test_when_seats_run_short_the_rider_dearest_to_carry_is_left_out():
    # Furthest-first alone reaches `far` first and spends the only seat on them.
    instance = _one_seat_two_riders()
    solution = greedy.solve(instance)

    assert validate(instance, solution) == []
    assert solution.unassigned == ("far",)
