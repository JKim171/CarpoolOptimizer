import pytest

from carpool_domain import (
    DESTINATION,
    Location,
    Participant,
    ProblemInstance,
    Role,
    TravelMatrix,
)

ARRIVAL = 1_000_000

# Hand-chosen so every quantity in the tests can be verified by inspection.
_SYMMETRIC = {
    ("d", "a"): 120,
    ("d", "b"): 240,
    ("a", "b"): 60,
    ("d", DESTINATION): 300,
    ("a", DESTINATION): 240,
    ("b", DESTINATION): 180,
}


def _matrix() -> TravelMatrix:
    durations = {}
    for (x, y), seconds in _SYMMETRIC.items():
        durations[(x, y)] = seconds
        durations[(y, x)] = seconds
    return TravelMatrix(durations)


@pytest.fixture
def instance() -> ProblemInstance:
    """One driver with two seats, two passengers, a shared destination."""
    return ProblemInstance(
        destination=Location(43.07, -89.41),
        arrival_by=ARRIVAL,
        participants=(
            Participant("d", Location(43.08, -89.43), role=Role.DRIVER, seats=2),
            Participant("a", Location(43.07, -89.42)),
            Participant("b", Location(43.06, -89.40)),
        ),
        matrix=_matrix(),
    )
