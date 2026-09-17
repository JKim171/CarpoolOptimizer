"""The geocoding endpoints and the cache behind them, against real Postgres.

The provider is substituted for a recording stub -- these tests are about what the *cache* does, and
a test that called ORS would need a key, spend quota, and fail when someone else's network did.
What is worth pinning here is that a second request costs no provider call, that an expired row is
re-resolved rather than renewed, and that a doubtful match is never cached as if it were certain.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from carpool_api.adapters.geocoding import GeocodingUnavailable, Place
from carpool_api.models import GeocodeCache

ADDRESS = "1500 E Medical Center Dr, Ann Arbor, MI"
LAT, LNG = 42.2830, -83.7302


class StubGeocoder:
    """Records every call, so "did this cost a provider request?" is a direct assertion."""

    def __init__(self, places=None, *, raises=None):
        self._places = places
        self._raises = raises
        self.searches: list[str] = []
        self.autocompletes: list[str] = []

    def _answer(self, text_query):
        if self._raises is not None:
            raise self._raises
        if self._places is not None:
            return self._places
        return [Place(address=text_query, lat=LAT, lng=LNG, confidence=0.9, is_approximate=False)]

    async def search(self, text_query, *, limit):
        self.searches.append(text_query)
        return self._answer(text_query)

    async def autocomplete(self, text_query, *, limit):
        self.autocompletes.append(text_query)
        return self._answer(text_query)


@pytest.fixture
async def geocoding_client(engine):
    """The real app with only `get_session` and the geocoder replaced.

    Yields the client together with the stub, so a test can read back what the provider was asked.
    """
    from carpool_api.db import get_session
    from carpool_api.main import create_app
    from carpool_api.routes.geocoding import get_geocoder

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    stub = StubGeocoder()

    async def override_session():
        async with sessionmaker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_geocoder] = lambda: stub

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://carpool.test"
    ) as client:
        yield client, stub, sessionmaker


@pytest.fixture(autouse=True)
async def clean_cache(engine):
    """The cache is keyed by address, not by event, so it outlives any one test's data."""
    async with engine.begin() as connection:
        await connection.execute(text("delete from geocode_cache"))


class TestResolution:
    async def test_an_address_resolves_and_is_cached(self, geocoding_client):
        client, stub, sessionmaker = geocoding_client

        response = await client.post("/v1/geocode", json={"addresses": [ADDRESS]})

        assert response.status_code == 200
        [result] = response.json()["results"]
        assert result["query"] == ADDRESS
        assert result["from_cache"] is False
        assert (result["place"]["lat"], result["place"]["lng"]) == (LAT, LNG)

        async with sessionmaker() as session:
            rows = (await session.execute(select(GeocodeCache))).scalars().all()
        assert len(rows) == 1
        assert rows[0].provider == "ors"

    async def test_a_second_request_costs_no_provider_call(self, geocoding_client):
        client, stub, _ = geocoding_client

        await client.post("/v1/geocode", json={"addresses": [ADDRESS]})
        response = await client.post("/v1/geocode", json={"addresses": [ADDRESS]})

        assert response.json()["results"][0]["from_cache"] is True
        assert stub.searches == [ADDRESS], "the cached address was geocoded twice"

    async def test_the_cache_key_ignores_case_and_spacing(self, geocoding_client):
        """`normalize_address` is shared with the solve fingerprint, so the two cannot disagree
        about whether two spellings are the same place."""
        client, stub, _ = geocoding_client

        await client.post("/v1/geocode", json={"addresses": [ADDRESS]})
        response = await client.post("/v1/geocode", json={"addresses": [f"  {ADDRESS.upper()}  "]})

        assert response.json()["results"][0]["from_cache"] is True
        assert len(stub.searches) == 1

    async def test_a_repeated_address_within_one_batch_is_geocoded_once(self, geocoding_client):
        """A pasted roster with two people at one house must not cost two calls."""
        client, stub, _ = geocoding_client

        response = await client.post("/v1/geocode", json={"addresses": [ADDRESS, ADDRESS]})

        assert len(response.json()["results"]) == 2
        assert len(stub.searches) == 1

    async def test_results_line_up_with_the_addresses_asked_for(self, geocoding_client):
        """The client matches these against roster rows by position. A missing entry for the
        unmatched address would shift every later address onto the wrong person."""
        client, stub, _ = geocoding_client
        stub._places = []  # nothing matches

        addresses = ["first", "second", "third"]
        response = await client.post("/v1/geocode", json={"addresses": addresses})

        results = response.json()["results"]
        assert [item["query"] for item in results] == addresses
        assert all(item["place"] is None for item in results)

    async def test_nothing_is_cached_when_nothing_matched(self, geocoding_client):
        client, stub, sessionmaker = geocoding_client
        stub._places = []

        await client.post("/v1/geocode", json={"addresses": [ADDRESS]})

        async with sessionmaker() as session:
            assert (await session.execute(select(GeocodeCache))).scalars().all() == []


class TestApproximateMatches:
    async def test_an_approximate_match_is_returned_but_not_cached(self, geocoding_client):
        """Caching it would mean reading it back later with no record of how doubtful it was, and
        reporting it as precise -- the silent failure that distorts a whole solve."""
        client, stub, sessionmaker = geocoding_client
        stub._places = [
            Place(address="Ann Arbor, MI", lat=LAT, lng=LNG, confidence=0.3, is_approximate=True)
        ]

        response = await client.post("/v1/geocode", json={"addresses": [ADDRESS]})

        assert response.json()["results"][0]["place"]["is_approximate"] is True
        async with sessionmaker() as session:
            assert (await session.execute(select(GeocodeCache))).scalars().all() == []

    async def test_a_cache_hit_never_claims_a_confidence_it_did_not_measure(self, geocoding_client):
        client, stub, _ = geocoding_client

        await client.post("/v1/geocode", json={"addresses": [ADDRESS]})
        response = await client.post("/v1/geocode", json={"addresses": [ADDRESS]})

        place = response.json()["results"][0]["place"]
        assert place["confidence"] is None
        assert place["is_approximate"] is False


class TestExpiry:
    async def test_an_expired_row_is_re_resolved_and_replaced(self, geocoding_client):
        """Expiry must re-ask the provider, not extend `expires_at`. Renewing in place would turn
        the cache into the permanent store of provider output design 5.2 exists to avoid."""
        client, stub, sessionmaker = geocoding_client
        await client.post("/v1/geocode", json={"addresses": [ADDRESS]})

        async with sessionmaker() as session:
            row = (await session.execute(select(GeocodeCache))).scalar_one()
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.merge(row)
            await session.commit()

        response = await client.post("/v1/geocode", json={"addresses": [ADDRESS]})

        assert response.json()["results"][0]["from_cache"] is False
        assert len(stub.searches) == 2, "the expired entry was served instead of re-resolved"
        async with sessionmaker() as session:
            refreshed = (await session.execute(select(GeocodeCache))).scalar_one()
        assert refreshed.expires_at > datetime.now(UTC)


class TestFailureModes:
    async def test_a_provider_outage_is_503_not_500(self, geocoding_client):
        """A dependency being down is not this service breaking, and the UI answers a 503 by
        letting the coordinator place the pin by hand."""
        client, stub, _ = geocoding_client
        stub._raises = GeocodingUnavailable("could not reach the geocoder")

        response = await client.post("/v1/geocode", json={"addresses": [ADDRESS]})

        assert response.status_code == 503

    async def test_an_empty_batch_is_rejected(self, geocoding_client):
        client, _, _ = geocoding_client

        response = await client.post("/v1/geocode", json={"addresses": []})

        assert response.status_code == 422

    async def test_an_oversized_batch_is_rejected(self, geocoding_client):
        """The cap exists so one request cannot spend the shared daily quota."""
        client, _, _ = geocoding_client

        response = await client.post("/v1/geocode", json={"addresses": ["x"] * 61})

        assert response.status_code == 422

    async def test_unknown_fields_are_rejected(self, geocoding_client):
        client, _, _ = geocoding_client

        response = await client.post(
            "/v1/geocode", json={"addresses": [ADDRESS], "provider": "google"}
        )

        assert response.status_code == 422


class TestAutocomplete:
    async def test_suggestions_come_back(self, geocoding_client):
        client, stub, _ = geocoding_client

        response = await client.get("/v1/geocode/autocomplete", params={"q": "1500 E Med"})

        assert response.status_code == 200
        assert response.json()["suggestions"][0]["lat"] == LAT
        assert stub.autocompletes == ["1500 E Med"]

    async def test_a_short_query_is_rejected_without_calling_the_provider(self, geocoding_client):
        """A two-character prefix matches most of the country, and autocomplete fires per
        keystroke -- against a 100/min limit."""
        client, stub, _ = geocoding_client

        response = await client.get("/v1/geocode/autocomplete", params={"q": "12"})

        assert response.status_code == 422
        assert stub.autocompletes == []

    async def test_suggestions_are_not_cached(self, geocoding_client):
        """`geocode_cache` is keyed by a full normalized address; a prefix is not one."""
        client, _, sessionmaker = geocoding_client

        await client.get("/v1/geocode/autocomplete", params={"q": "1500 E Med"})

        async with sessionmaker() as session:
            assert (await session.execute(select(GeocodeCache))).scalars().all() == []
