"""The provider client, against a mocked transport.

No network and no key: `httpx.MockTransport` answers every request, so these run in CI and pin the
parsing decisions that are expensive to get wrong -- above all the coordinate order, which fails
silently (docs/design.md 4.4).
"""

import httpx
import pytest

from carpool_api.adapters.geocoding import (
    LOW_CONFIDENCE,
    GeocodingUnavailable,
    OrsGeocoder,
    _parse_features,
)
from carpool_api.config import Settings

# Asymmetric, and on opposite sides of the equator/meridian from each other, so a lat/lng swap
# cannot land somewhere plausible. Same reasoning as the geo.py coordinate tests.
LNG = -83.7430
LAT = 42.2808


def feature(
    *, lng=LNG, lat=LAT, label="123 Main St, Ann Arbor, MI", layer="address", confidence=0.9
):
    return {
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": {"label": label, "layer": layer, "confidence": confidence},
    }


def settings(**overrides):
    base = {
        "database_url": "postgresql+asyncpg://unused/unused",
        "ors_api_key": "test-key",
    }
    return Settings(**{**base, **overrides})


def geocoder_returning(payload, *, status_code=200, capture=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(status_code, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OrsGeocoder(settings(), client=client)


class TestParsing:
    def test_coordinates_are_lng_lat_and_are_not_swapped(self):
        """The failure this prevents raises no error and produces no wrong type -- only drivers
        sent to the wrong place. Pinned here and in geo.py, at both ends of the system."""
        [place] = _parse_features({"features": [feature()]})

        assert place.lat == LAT
        assert place.lng == LNG

    def test_a_street_level_match_is_not_approximate(self):
        [place] = _parse_features({"features": [feature(layer="address", confidence=0.9)]})

        assert place.is_approximate is False
        assert place.confidence == pytest.approx(0.9)

    @pytest.mark.parametrize("layer", ["locality", "region", "county", None])
    def test_a_coarser_layer_is_approximate(self, layer):
        """A town centroid standing in for a house is the silent, catastrophic failure -- one bad
        coordinate distorts the whole solve (docs/design.md 7.2)."""
        [place] = _parse_features({"features": [feature(layer=layer, confidence=0.95)]})

        assert place.is_approximate is True

    def test_low_confidence_is_approximate_even_at_address_level(self):
        [place] = _parse_features(
            {"features": [feature(layer="address", confidence=LOW_CONFIDENCE - 0.01)]}
        )

        assert place.is_approximate is True

    def test_a_missing_confidence_is_not_treated_as_certain(self):
        payload = {
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [LNG, LAT]},
                    "properties": {"label": "somewhere", "layer": "address"},
                }
            ]
        }

        [place] = _parse_features(payload)

        assert place.confidence == 0.0
        assert place.is_approximate is True

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"features": None},
            {"features": [{"geometry": {"coordinates": [LNG]}, "properties": {"label": "x"}}]},
            {"features": [{"geometry": {"coordinates": ["a", "b"]}, "properties": {"label": "x"}}]},
            {"features": [{"geometry": {"coordinates": [LNG, LAT]}, "properties": {}}]},
            {"features": ["not a feature"]},
            "not a dict",
        ],
    )
    def test_malformed_features_are_skipped_rather_than_raising(self, payload):
        """A provider response that changed shape must degrade to "no match", which the UI already
        handles by letting the coordinator place the pin. A parse crash would be a 500."""
        assert _parse_features(payload) == []


class TestProviderCalls:
    async def test_search_sends_the_key_and_the_country_boundary(self):
        captured = []
        geocoder = geocoder_returning({"features": [feature()]}, capture=captured)

        await geocoder.search("123 Main St", limit=1)

        [request] = captured
        assert request.url.params["api_key"] == "test-key"
        assert request.url.params["text"] == "123 Main St"
        assert request.url.params["boundary.country"] == "USA"
        assert request.url.path == "/geocode/search"

    async def test_autocomplete_uses_its_own_endpoint(self):
        captured = []
        geocoder = geocoder_returning({"features": [feature()]}, capture=captured)

        await geocoder.autocomplete("123 Mai", limit=5)

        assert captured[0].url.path == "/geocode/autocomplete"

    async def test_a_missing_key_is_unavailable_not_a_crash(self):
        geocoder = OrsGeocoder(settings(ors_api_key=None))

        with pytest.raises(GeocodingUnavailable, match="not configured"):
            await geocoder.search("anywhere", limit=1)

    async def test_rate_limiting_says_so(self):
        """429 is the one provider failure a coordinator can act on -- waiting works."""
        geocoder = geocoder_returning({}, status_code=429)

        with pytest.raises(GeocodingUnavailable, match="rate limit"):
            await geocoder.search("anywhere", limit=1)

    async def test_a_provider_error_does_not_leak_the_key(self):
        geocoder = geocoder_returning({"error": "bad api_key test-key"}, status_code=403)

        with pytest.raises(GeocodingUnavailable) as caught:
            await geocoder.search("anywhere", limit=1)

        assert "test-key" not in str(caught.value)

    async def test_a_network_failure_becomes_unavailable(self):
        def handler(request):
            raise httpx.ConnectError("no route to host")

        geocoder = OrsGeocoder(
            settings(), client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )

        with pytest.raises(GeocodingUnavailable, match="could not reach"):
            await geocoder.search("anywhere", limit=1)
