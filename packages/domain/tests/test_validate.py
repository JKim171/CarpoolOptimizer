from dataclasses import replace

from carpool_domain import Role, Route, Solution, validate


def codes(violations):
    return {v.code for v in violations}


def test_a_complete_feasible_solution_has_no_violations(instance):
    solution = Solution(routes=(Route("d", outbound=("a", "b"), inbound=("b", "a")),))
    assert validate(instance, solution) == []


def test_everyone_must_be_accounted_for(instance):
    solution = Solution(routes=(Route("d", outbound=("a",), inbound=("a",)),))
    assert codes(validate(instance, solution)) == {"missing_assignment"}


def test_capacity_is_enforced(instance):
    one_seat = replace(
        instance,
        participants=(
            replace(instance.participant("d"), seats=1),
            instance.participant("a"),
            instance.participant("b"),
        ),
    )
    solution = Solution(routes=(Route("d", outbound=("a", "b"), inbound=("b", "a")),))
    assert "capacity_exceeded" in codes(validate(one_seat, solution))


def test_a_passenger_cannot_be_assigned_twice(instance):
    solution = Solution(
        routes=(Route("d", outbound=("a", "b"), inbound=("b", "a")),), unassigned=("a",)
    )
    assert "duplicate_assignment" in codes(validate(instance, solution))


def test_non_drivers_cannot_drive(instance):
    passenger_driver = replace(
        instance,
        participants=(
            replace(instance.participant("d"), role=Role.PASSENGER),
            instance.participant("a"),
            instance.participant("b"),
        ),
    )
    solution = Solution(routes=(Route("d", outbound=("a", "b"), inbound=("b", "a")),))
    assert "driver_cannot_drive" in codes(validate(passenger_driver, solution))


def test_detour_cap_is_enforced(instance):
    impatient = replace(
        instance,
        participants=(
            replace(instance.participant("d"), max_detour_seconds=60),
            instance.participant("a"),
            instance.participant("b"),
        ),
    )
    solution = Solution(routes=(Route("d", outbound=("a", "b"), inbound=("b", "a")),))
    assert "detour_exceeded" in codes(validate(impatient, solution))


def test_pins_are_enforced(instance):
    pinned = replace(
        instance,
        participants=(
            instance.participant("d"),
            replace(instance.participant("a"), pinned_driver_id="someone_else"),
            instance.participant("b"),
        ),
    )
    solution = Solution(routes=(Route("d", outbound=("a", "b"), inbound=("b", "a")),))
    assert "pin_violated" in codes(validate(pinned, solution))


def test_a_rider_who_needs_a_leg_must_be_on_it(instance):
    solution = Solution(routes=(Route("d", outbound=("a", "b"), inbound=("b",)),))
    violations = [v for v in validate(instance, solution) if v.code == "leg_missing"]
    assert [v.participant_id for v in violations] == ["a"]


def test_pickup_cannot_precede_a_participants_earliest_departure(instance):
    late_riser = replace(
        instance,
        participants=(
            instance.participant("d"),
            replace(instance.participant("a"), earliest_departure=instance.arrival_by),
            instance.participant("b"),
        ),
    )
    solution = Solution(routes=(Route("d", outbound=("a", "b"), inbound=("b", "a")),))
    assert "early_pickup" in codes(validate(late_riser, solution))
