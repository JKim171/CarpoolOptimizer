"""The routing provider client, against a mocked transport.

No network and no key: `httpx.MockTransport` answers every request. What is pinned here is what
fails silently when wrong -- the coordinate order, which row and column a duration is read from, and
the rounding to integer seconds -- and that every way the provider can fail ends in the fallback
rather than in a failed solve.
"""

import json

import httpx
import pytest

from carpool_api.adapters.travel import (
    OrsMatrix,
    TravelUnavailable,
    estimates_or_fallback,
    haversine_estimates,
    parse_matrix,
)
from carpool_api.config import Settings
from carpool_domain import DESTINATION, Location

# Asymmetric in sign and magnitude, so a lat/lng swap cannot land somewhere plausible.
NODES = {
    DESTINATION: Location(lat=42.2808, lng=-83.7430),
    "a": Location(lat=42.3000, lng=-83.7000),
    "b": Location(lat=42.2500, lng=-83.8000),
}

# Directed on purpose: every cell differs from its transpose, so reading [j][i] for [i][j] fails.
DURATIONS = [
    [0.0, 600.4, 700.6],
    [610.0, 0.0, 300.2],
    [720.0, 310.0, 0.0],
]
DISTANCES = [
    [0.0, 8000.4, 9000.6],
    [8100.0, 0.0, 4000.0],
    [9200.0, 4100.0, 0.0],
]


def matrix_payload(durations=DURATIONS, distances=DISTANCES):
    return {"durations": durations, "distances": distances}


def settings(**overrides):
    base = {
        "database_url": "postgresql+asyncpg://unused/unused",
        "ors_api_key": "test-key",
    }
    return Settings(**{**base, **overrides})


def matrix_answering(handler, **overrides):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OrsMatrix(settings(**overrides), client=client)


def returning(payload, *, status_code=200, capture=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(status_code, json=payload)

    return handler


class TestParsing:
    def test_cells_are_read_row_to_column(self):
        estimates = parse_matrix(matrix_payload(), [DESTINATION, "a", "b"])

        assert estimates.matrix.duration(DESTINATION, "a") == 600
        assert estimates.matrix.duration("a", DESTINATION) == 610
        assert estimates.matrix.duration("a", "b") == 300
        assert estimates.matrix.duration("b", "a") == 310
        assert estimates.distance_m("b", DESTINATION) == 9200

    def test_floats_are_rounded_to_integers(self):
        estimates = parse_matrix(matrix_payload(), [DESTINATION, "a", "b"])

        assert estimates.matrix.duration(DESTINATION, "b") == 701
        assert estimates.distance_m(DESTINATION, "b") == 9001
        assert isinstance(estimates.matrix.duration(DESTINATION, "b"), int)

    def test_the_answer_says_it_is_road_times(self):
        assert parse_matrix(matrix_payload(), [DESTINATION, "a", "b"]).provider == "ors"

    def test_an_unroutable_point_is_left_out_not_guessed(self):
        """An address that cannot be snapped nulls its whole row and column. Any number put in
        those cells would be a straight-line guess passing as a road time, so the person goes."""
        durations = [row[:] for row in DURATIONS]
        for k in range(3):
            if k != 2:
                durations[2][k] = durations[k][2] = None

        estimates = parse_matrix(matrix_payload(durations=durations), [DESTINATION, "a", "b"])

        assert estimates.unroutable == frozenset({"b"})
        assert estimates.provider == "ors"
        assert estimates.matrix.duration("a", DESTINATION) == 610
        with pytest.raises(KeyError):
            estimates.matrix.duration("a", "b")
        with pytest.raises(KeyError):
            estimates.distance_m(DESTINATION, "b")

    def test_a_null_distance_counts_as_much_as_a_null_duration(self):
        distances = [row[:] for row in DISTANCES]
        distances[0][1] = distances[1][0] = distances[1][2] = distances[2][1] = None

        estimates = parse_matrix(matrix_payload(distances=distances), [DESTINATION, "a", "b"])

        assert estimates.unroutable == frozenset({"a"})

    def test_one_missing_pair_costs_one_of_the_two(self):
        """Two points with no road between them -- an island -- need only one of them gone."""
        nodes = [DESTINATION, "a", "b", "c", "d"]
        durations = [[0.0 if i == j else 100.0 + i + j for j in range(5)] for i in range(5)]
        durations[1][2] = None

        estimates = parse_matrix({"durations": durations, "distances": durations}, nodes)

        assert estimates.unroutable == frozenset({"a"})
        assert estimates.matrix.duration("b", "c") == 105

    def test_snap_distances_are_read_per_node_and_rounded(self):
        sources = [{"snapped_distance": 3.4}, {"snapped_distance": 412.6}, {"location": [0, 0]}]
        payload = {**matrix_payload(), "sources": sources}

        estimates = parse_matrix(payload, [DESTINATION, "a", "b"])

        assert estimates.snapped_m == {DESTINATION: 3, "a": 413}

    @pytest.mark.parametrize("sources", [None, [], [{"snapped_distance": 1.0}], "x"])
    def test_odd_snap_distances_never_refuse_the_answer(self, sources):
        """They are a hint for the organizer, not part of the travel times."""
        estimates = parse_matrix({**matrix_payload(), "sources": sources}, [DESTINATION, "a", "b"])

        assert estimates.snapped_m == {}
        assert estimates.provider == "ors"

    def test_a_routable_roster_leaves_nobody_out(self):
        assert parse_matrix(matrix_payload(), [DESTINATION, "a", "b"]).unroutable == frozenset()

    def test_an_unroutable_destination_is_unavailable(self):
        """Without the destination there is nothing to solve, so everyone goes to estimates."""
        nodes = [DESTINATION, "a", "b", "c"]
        square = [[0.0 if i == j else 50.0 for j in range(4)] for i in range(4)]
        for k in (1, 2, 3):
            square[0][k] = square[k][0] = None

        with pytest.raises(TravelUnavailable, match="destination"):
            parse_matrix({"durations": square, "distances": square}, nodes)

    def test_losing_most_of_the_roster_is_unavailable(self):
        """Half the addresses failing at once is the provider failing, not the addresses."""
        nodes = [DESTINATION, "a", "b", "c"]
        square = [[0.0 if i == j else 50.0 for j in range(4)] for i in range(4)]
        for bad in (1, 2):
            for k in range(4):
                if k != bad:
                    square[bad][k] = square[k][bad] = None

        with pytest.raises(TravelUnavailable, match="most"):
            parse_matrix({"durations": square, "distances": square}, nodes)

    @pytest.mark.parametrize(
        "payload",
        [
            [],
            {},
            {"durations": DURATIONS},
            {"durations": DURATIONS[:2], "distances": DISTANCES},
            {"durations": [[0.0, 1.0], [1.0, 0.0], [1.0, 1.0]], "distances": DISTANCES},
            {"durations": [[0.0, "x", 1.0], *DURATIONS[1:]], "distances": DISTANCES},
        ],
    )
    def test_a_malformed_response_is_unavailable(self, payload):
        with pytest.raises(TravelUnavailable):
            parse_matrix(payload, [DESTINATION, "a", "b"])


class TestRequest:
    async def test_locations_are_sent_lng_first_in_node_order(self):
        """The failure this prevents raises nothing -- ORS would happily route the swapped points,
        somewhere in Antarctica."""
        sent: list[httpx.Request] = []
        await matrix_answering(returning(matrix_payload(), capture=sent)).estimates(NODES)

        body = json.loads(sent[0].content)
        assert body["locations"] == [[loc.lng, loc.lat] for loc in NODES.values()]
        assert sorted(body["metrics"]) == ["distance", "duration"]

    async def test_one_request_for_the_whole_square(self):
        sent: list[httpx.Request] = []
        await matrix_answering(returning(matrix_payload(), capture=sent)).estimates(NODES)

        [request] = sent
        body = json.loads(request.content)
        # No sources or destinations: every location against every other, both legs at once.
        assert "sources" not in body
        assert "destinations" not in body

    async def test_the_key_travels_in_a_header_not_the_url(self):
        sent: list[httpx.Request] = []
        await matrix_answering(returning(matrix_payload(), capture=sent)).estimates(NODES)

        [request] = sent
        assert request.headers["Authorization"] == "test-key"
        assert "test-key" not in str(request.url)

    async def test_routing_lives_under_its_own_prefix(self):
        sent: list[httpx.Request] = []
        matrix = matrix_answering(
            returning(matrix_payload(), capture=sent), ors_base_url="https://ors.test/"
        )
        await matrix.estimates(NODES)

        assert str(sent[0].url) == "https://ors.test/openrouteservice/v2/matrix/driving-car"


class TestFailure:
    @pytest.mark.parametrize("status_code", [401, 403, 429, 500, 503])
    async def test_an_error_status_is_unavailable(self, status_code):
        matrix = matrix_answering(returning({"error": "no"}, status_code=status_code))

        with pytest.raises(TravelUnavailable, match=str(status_code)):
            await matrix.estimates(NODES)

    async def test_an_unreachable_provider_is_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        with pytest.raises(TravelUnavailable):
            await matrix_answering(handler).estimates(NODES)

    async def test_a_body_that_is_not_json_is_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>gateway</html>")

        with pytest.raises(TravelUnavailable):
            await matrix_answering(handler).estimates(NODES)

    async def test_no_key_makes_no_request(self):
        sent: list[httpx.Request] = []
        matrix = matrix_answering(returning(matrix_payload(), capture=sent), ors_api_key=None)

        with pytest.raises(TravelUnavailable):
            await matrix.estimates(NODES)
        assert sent == []


class TestFallback:
    async def test_the_providers_answer_when_it_has_one(self):
        estimates = await estimates_or_fallback(
            matrix_answering(returning(matrix_payload())), NODES
        )

        assert estimates.provider == "ors"
        assert estimates.matrix.duration(DESTINATION, "a") == 600

    async def test_straight_line_estimates_when_it_does_not(self):
        estimates = await estimates_or_fallback(
            matrix_answering(returning({}, status_code=429)), NODES
        )

        assert estimates.provider == "haversine"
        assert estimates.matrix.duration("a", "b") == haversine_estimates(NODES).matrix.duration(
            "a", "b"
        )
