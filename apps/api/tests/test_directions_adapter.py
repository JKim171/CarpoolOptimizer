"""The Directions client, against a mocked transport. No network and no key."""

import json

import httpx
import pytest

from carpool_api.adapters.directions import OrsDirections, parse_line
from carpool_api.adapters.travel import TravelUnavailable
from carpool_api.config import Settings
from carpool_domain import Location

STOPS = [Location(lat=42.3000, lng=-83.7000), Location(lat=42.2808, lng=-83.7430)]
LINE = [[-83.700011, 42.300105], [-83.72, 42.29], [-83.742990, 42.280811]]


def directions_payload(coordinates=LINE):
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coordinates}}
        ],
    }


def directions_answering(status_code=200, payload=None, capture=None, **overrides):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(status_code, json=payload or directions_payload())

    settings = Settings(
        **{
            "database_url": "postgresql+asyncpg://unused/unused",
            "ors_api_key": "test-key",
            **overrides,
        }
    )
    return OrsDirections(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_the_line_is_read_lng_first_as_sent():
    assert parse_line(directions_payload()) == [tuple(point) for point in LINE]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"features": []},
        {"features": [{"geometry": {"type": "Point", "coordinates": [0, 0]}}]},
        directions_payload(coordinates=[[-83.7, 42.3]]),
        directions_payload(coordinates=[[-83.7, 42.3], ["x", 42.2]]),
    ],
)
def test_a_malformed_response_is_unavailable(payload):
    with pytest.raises(TravelUnavailable):
        parse_line(payload)


async def test_waypoints_are_sent_lng_first_with_the_key_in_a_header():
    sent: list[httpx.Request] = []
    await directions_answering(capture=sent, ors_base_url="https://ors.test").line(STOPS)

    [request] = sent
    assert str(request.url) == "https://ors.test/openrouteservice/v2/directions/driving-car/geojson"
    assert json.loads(request.content)["coordinates"] == [[s.lng, s.lat] for s in STOPS]
    assert json.loads(request.content)["radiuses"] == [-1, -1]
    assert request.headers["Authorization"] == "test-key"
    assert "test-key" not in str(request.url)


@pytest.mark.parametrize("status_code", [404, 429, 500])
async def test_an_error_status_is_unavailable(status_code):
    with pytest.raises(TravelUnavailable, match=str(status_code)):
        await directions_answering(status_code=status_code, payload={"error": "no"}).line(STOPS)


async def test_no_key_makes_no_request():
    sent: list[httpx.Request] = []
    with pytest.raises(TravelUnavailable):
        await directions_answering(capture=sent, ors_api_key=None).line(STOPS)
    assert sent == []
