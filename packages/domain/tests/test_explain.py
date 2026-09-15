"""Diagnosing why a rider was left out.

Each test builds an instance where exactly one rule can be the culprit, then asserts the diagnosis
names that rule. A reason that merely looks plausible is worse than no reason at all: an organizer
told "every car is full" will go recruiting drivers when the real problem was one person's detour
cap.
"""

from dataclasses import replace

import pytest

from carpool_domain import (
    Constraint,
    Location,
    Participant,
    ProblemInstance,
    Role,
    Solution,
    greedy,
    unassigned_reason,
)


def solve_and_diagnose(instance: ProblemInstance) -> dict[str, Constraint]:
    solution = greedy.solve(instance)
    return {
        participant_id: unassigned_reason(instance, solution, participant_id)
        for participant_id in solution.unassigned
    }


def test_nobody_is_unassigned_in_a_feasible_instance(instance):
    """The guard for every test below: they only mean something if this one holds."""
    assert greedy.solve(instance).unassigned == ()


def test_no_drivers_at_all_is_reported_as_role(instance):
    """Not "the cars are full" -- there are no cars."""
    passengers_only = replace(
        instance,
        participants=tuple(replace(p, role=Role.PASSENGER, seats=0) for p in instance.participants),
    )

    diagnosis = solve_and_diagnose(passengers_only)

    assert set(diagnosis) == {"d", "a", "b"}
    assert set(diagnosis.values()) == {Constraint.ROLE}


def test_a_full_car_is_reported_as_seats(instance):
    one_seat = replace(
        instance,
        participants=tuple(
            replace(p, seats=1) if p.id == "d" else p for p in instance.participants
        ),
    )

    diagnosis = solve_and_diagnose(one_seat)

    assert len(diagnosis) == 1
    assert set(diagnosis.values()) == {Constraint.SEATS}


def test_a_detour_cap_is_reported_as_detour(instance):
    """Seats are free and the timing is fine; only the driver's own cap excludes the rider."""
    capped = replace(
        instance,
        participants=tuple(
            replace(p, max_detour_seconds=0) if p.id == "d" else p for p in instance.participants
        ),
    )

    diagnosis = solve_and_diagnose(capped)

    assert diagnosis
    assert set(diagnosis.values()) == {Constraint.DETOUR}


def test_a_time_window_is_reported_as_time(instance):
    """`a` cannot leave before the event has already started, so no pickup time works."""
    impossible_window = replace(
        instance,
        participants=tuple(
            replace(p, earliest_departure=instance.arrival_by + 3_600) if p.id == "a" else p
            for p in instance.participants
        ),
    )

    diagnosis = solve_and_diagnose(impossible_window)

    assert diagnosis.get("a") is Constraint.TIME


def test_a_pin_to_a_passenger_is_reported_as_role(instance):
    """Pinned to someone who cannot drive: nobody could have carried them."""
    bad_pin = replace(
        instance,
        participants=tuple(
            replace(p, pinned_driver_id="b") if p.id == "a" else p for p in instance.participants
        ),
    )

    diagnosis = solve_and_diagnose(bad_pin)

    assert diagnosis.get("a") is Constraint.ROLE


def test_a_pin_to_a_driver_with_no_room_is_reported_as_seats(instance):
    """The pin is honourable in principle; the seat is what is missing."""
    crowded = replace(
        instance,
        participants=(
            replace(instance.participant("d"), seats=1),
            replace(instance.participant("a"), pinned_driver_id="d"),
            replace(instance.participant("b"), pinned_driver_id="d"),
        ),
    )

    diagnosis = solve_and_diagnose(crowded)

    assert len(diagnosis) == 1
    assert set(diagnosis.values()) == {Constraint.SEATS}


def test_a_pin_to_an_unknown_participant_is_reported_as_role(instance):
    """The API rejects such a pin (`_validate_pin`), so this is the defence behind that."""
    dangling = replace(
        instance,
        participants=tuple(
            replace(p, pinned_driver_id="ghost") if p.id == "a" else p
            for p in instance.participants
        ),
    )

    diagnosis = solve_and_diagnose(dangling)

    assert diagnosis.get("a") is Constraint.ROLE


def test_seats_are_reported_before_a_detour_cap_when_both_bind(instance):
    """Ordering is deliberate: the cars being full is what an organizer can act on first."""
    both = replace(
        instance,
        participants=tuple(
            replace(p, seats=0, max_detour_seconds=0) if p.id == "d" else p
            for p in instance.participants
        ),
    )

    diagnosis = solve_and_diagnose(both)

    assert set(diagnosis.values()) == {Constraint.SEATS}


def test_every_unassigned_participant_gets_a_reason(instance):
    """The column is not-null, so the function must be total over `solution.unassigned`."""
    hopeless = replace(
        instance,
        participants=(
            replace(instance.participant("d"), role=Role.PASSENGER, seats=0),
            instance.participant("a"),
            instance.participant("b"),
        ),
    )
    solution = greedy.solve(hopeless)

    assert solution.unassigned
    for participant_id in solution.unassigned:
        assert isinstance(unassigned_reason(hopeless, solution, participant_id), Constraint)


def test_an_unknown_participant_id_raises(instance):
    """A caller asking about somebody not on the event is a bug, not an empty answer."""
    with pytest.raises(KeyError):
        unassigned_reason(instance, Solution(), "nobody")


def test_diagnosis_does_not_mutate_the_solution(instance):
    """Relaxation builds throwaway routes; it must not touch the one being explained."""
    one_seat = replace(
        instance,
        participants=tuple(
            replace(p, seats=1) if p.id == "d" else p for p in instance.participants
        ),
    )
    solution = greedy.solve(one_seat)
    before = (solution.routes, solution.unassigned)

    for participant_id in solution.unassigned:
        unassigned_reason(one_seat, solution, participant_id)

    assert (solution.routes, solution.unassigned) == before


def test_participants_needing_no_legs_are_not_in_the_solution(instance):
    """Someone arranging their own transport is absent by design, so nothing to diagnose."""
    self_driving = replace(
        instance,
        participants=tuple(
            replace(p, needs_outbound=False, needs_return=False) if p.id == "b" else p
            for p in instance.participants
        ),
    )

    solution = greedy.solve(self_driving)

    assert "b" not in solution.unassigned


def test_the_instance_is_untouched_by_diagnosis(instance):
    """`ProblemInstance` is frozen; this pins that the diagnosis path respects it."""
    before = instance.participants
    arrival, ends = instance.arrival_by, instance.ends_at

    solve_and_diagnose(instance)

    assert instance.participants == before
    assert (instance.arrival_by, instance.ends_at) == (arrival, ends)
    assert Participant("x", Location(0.0, 0.0)).role is Role.PASSENGER
