from dataclasses import replace

import pytest

from carpool_domain import (
    DESTINATION,
    Location,
    Participant,
    ProblemInstance,
    Role,
    Route,
    TravelMatrix,
    inbound_schedule,
    outbound_schedule,
)

ROUTE = Route("d", outbound=("a", "b"), inbound=("b", "a"))


def test_pickups_count_backward_from_the_arrival_deadline(instance):
    # d -> a -> b -> venue is 120 + 60 + 180 = 360 s: the driver leaves six minutes before arrival.
    arrival = instance.arrival_by
    assert outbound_schedule(instance, ROUTE) == {
        "d": arrival - 360,
        "a": arrival - 240,
        "b": arrival - 180,
        DESTINATION: arrival,
    }


def test_drop_offs_count_forward_from_the_event_end(instance):
    # venue -> b -> a -> d is 180 + 60 + 120 = 360 s after the event ends.
    ends = instance.ends_at
    assert inbound_schedule(instance, ROUTE) == {
        DESTINATION: ends,
        "b": ends + 180,
        "a": ends + 240,
        "d": ends + 360,
    }


def test_drop_offs_use_travel_times_away_from_the_venue():
    # With a one-way street, the drive home is not the drive in reversed. Scheduling the return
    # from the outbound durations would put this rider's drop-off 100 s early.
    durations = {
        ("D", "x"): 50,
        ("x", "D"): 70,
        ("x", DESTINATION): 200,
        (DESTINATION, "x"): 300,
        ("D", DESTINATION): 400,
        (DESTINATION, "D"): 450,
    }
    instance = ProblemInstance(
        destination=Location(0.0, 0.0),
        arrival_by=0,
        ends_at=10_000,
        participants=(
            Participant("D", Location(0.0, 0.0), role=Role.DRIVER, seats=1),
            Participant("x", Location(0.0, 0.0)),
        ),
        matrix=TravelMatrix(durations),
    )

    drop_offs = inbound_schedule(instance, Route("D", outbound=("x",), inbound=("x",)))

    assert drop_offs == {DESTINATION: 10_000, "x": 10_300, "D": 10_370}


@pytest.mark.parametrize("offset", [0, -1])
def test_the_event_must_end_after_everyone_arrives(instance, offset):
    with pytest.raises(ValueError, match="ends_at"):
        replace(instance, ends_at=instance.arrival_by + offset)
