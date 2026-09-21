"""The rate limiter itself, on a fake clock, and the backstop limit on every /v1 route.

The per-route limits -- event creation, geocoding, solves -- are tested against the real routes in
the integration suite, because what matters there is what each one charges and when.
"""

import pytest

from carpool_api.ratelimit import GENERAL, RateLimited, RateLimiter, Rule

RULE = Rule("test", 3, 60, "Slow down")


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def limiter(clock: Clock) -> RateLimiter:
    return RateLimiter(clock=clock)


class TestBucket:
    def test_the_limit_is_allowed_and_the_next_is_refused(self, limiter):
        for _ in range(3):
            limiter.hit(RULE, "a")

        with pytest.raises(RateLimited) as caught:
            limiter.hit(RULE, "a")

        # One unit refills every 20 seconds (3 per 60).
        assert caught.value.retry_after == 20
        assert str(caught.value) == "Slow down; try again in 20 seconds."

    def test_units_refill_continuously(self, limiter, clock):
        for _ in range(3):
            limiter.hit(RULE, "a")

        clock.now += 20
        limiter.hit(RULE, "a")
        with pytest.raises(RateLimited):
            limiter.hit(RULE, "a")

    def test_a_refill_never_exceeds_the_limit(self, limiter, clock):
        """Idle for an hour is still only three in a burst, not sixty."""
        clock.now += 3600
        for _ in range(3):
            limiter.hit(RULE, "a")

        with pytest.raises(RateLimited):
            limiter.hit(RULE, "a")

    def test_clients_do_not_share_an_allowance(self, limiter):
        for _ in range(3):
            limiter.hit(RULE, "a")

        limiter.hit(RULE, "b")

    def test_rules_do_not_share_an_allowance(self, limiter):
        for _ in range(3):
            limiter.hit(RULE, "a")

        limiter.hit(Rule("other", 3, 60, "Other"), "a")

    def test_a_cost_too_large_spends_nothing(self, limiter):
        """All or nothing: a batch refused for being too big must not use up what was left."""
        limiter.hit(RULE, "a")

        with pytest.raises(RateLimited):
            limiter.hit(RULE, "a", cost=3)

        limiter.hit(RULE, "a", cost=2)

    def test_a_zero_cost_is_always_allowed(self, limiter):
        """A geocoding batch served entirely from cache charges zero lookups."""
        limiter.hit(RULE, "a", cost=3)

        limiter.hit(RULE, "a", cost=0)

    def test_long_waits_are_described_in_hours(self, limiter):
        daily = Rule("daily", 1, 86_400, "Daily limit reached")
        limiter.hit(daily, "a")

        with pytest.raises(RateLimited) as caught:
            limiter.hit(daily, "a")

        assert str(caught.value) == "Daily limit reached; try again in 24 hours."

    def test_a_single_unit_of_wait_is_singular(self, limiter):
        fast = Rule("fast", 1, 1, "Slow down")
        limiter.hit(fast, "a")

        with pytest.raises(RateLimited) as caught:
            limiter.hit(fast, "a")

        assert str(caught.value) == "Slow down; try again in 1 second."

    def test_refilled_buckets_are_forgotten(self, limiter, clock):
        """Memory is bounded by recent clients, not by every address ever seen."""
        for client in range(1023):
            limiter.hit(RULE, f"client-{client}")
        clock.now += 60

        limiter.hit(RULE, "the 1024th hit sweeps")

        assert limiter._buckets.keys() == {("test", "the 1024th hit sweeps")}


class TestBackstop:
    def test_v1_routes_are_limited_even_without_a_route_limit(self, client):
        """An unknown path still counts: the backstop runs before routing."""
        for _ in range(GENERAL.limit):
            assert client.get("/v1/nothing-here").status_code == 404

        response = client.get("/v1/nothing-here")

        assert response.status_code == 429
        assert int(response.headers["retry-after"]) >= 1
        assert response.json()["detail"].startswith("Too many requests; try again in")

    def test_health_checks_are_never_limited(self, client):
        """A limit that failed /healthz would turn load into container restarts."""
        for _ in range(GENERAL.limit + 5):
            assert client.get("/healthz").status_code == 200

    def test_a_429_is_readable_cross_origin(self, client):
        """Without CORS headers the browser hides the 429, and the UI reports a network error."""
        for _ in range(GENERAL.limit):
            client.get("/v1/nothing-here")

        response = client.get("/v1/nothing-here", headers={"Origin": "http://localhost:3000"})

        assert response.status_code == 429
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
