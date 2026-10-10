"""The committed example event must match what the generator, the solver and the schemas produce.

The `/demo` page renders `apps/web/lib/demo/event.json` as it stands. A solver or schema change that
did not regenerate it would leave the public page showing an answer the product no longer gives --
or a shape the results components no longer read -- with nothing in the web build to notice.
"""

import json
from pathlib import Path

from carpool_api.demo import build, render

EVENT = Path(__file__).resolve().parents[3] / "apps/web/lib/demo/event.json"


def test_committed_demo_matches_the_generator():
    assert EVENT.exists(), f"{EVENT} is missing; run `make demo`"
    assert render() == EVENT.read_text(encoding="utf-8"), (
        "The committed demo event is out of date; run `make demo` and commit the result."
    )


def test_everyone_rides_and_every_driver_carries_someone():
    """What the seed was picked for. An example where a car drives empty, or someone is left at
    home, is a worse advertisement than it is an example."""
    event = build()
    riders = {stop.participant_id for r in event.solution.routes for stop in r.outbound.stops}
    passengers = {p.id for p in event.people if p.role == "passenger"}

    assert event.solution.unassigned == []
    assert riders == passengers
    assert all(route.outbound.stops for route in event.solution.routes)


def test_nobody_in_the_example_has_a_street_address():
    """Generated people get a distance and a direction, never an address -- an invented one would
    put a fictional family at a real front door."""
    for route in build().solution.routes:
        for stop in route.outbound.stops + route.inbound.stops:
            assert stop.pickup_address.endswith(" of the courts")


def test_the_file_is_valid_json():
    json.loads(EVENT.read_text(encoding="utf-8"))
