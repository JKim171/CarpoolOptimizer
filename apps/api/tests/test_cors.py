"""CORS, which the web app cannot work without and which must not be wider than it needs.

The web app is deployed separately from the API (Vercel and the EC2 instance, docs/design.md 10.1),
so every browser call is cross-origin -- including in development, where `next dev` serves :3000 and
the API :8000. Without the middleware the browser refuses the response and the failure looks like
the API being down.
"""

from carpool_api.config import get_settings

ALLOWED = "http://localhost:3000"


def test_preflight_from_the_web_origin_is_allowed(client):
    response = client.options(
        "/v1/events",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_preflight_from_another_origin_is_not_allowed(client):
    """An unlisted origin gets no allow header, so the browser blocks the call.

    This is not the authorization boundary -- the organizer token is (docs/design.md 6.1) -- but a
    permissive `*` here would be a silent invitation to put one in a cookie later.
    """
    response = client.options(
        "/v1/events",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert "access-control-allow-origin" not in response.headers


def test_credentials_are_not_allowed(client):
    """`allow_credentials=True` plus a mistaken origin is how a cross-site request rides an
    existing session. Nothing here uses cookies, so the answer is to never permit them."""
    response = client.options(
        "/v1/events",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "POST"},
    )

    assert "access-control-allow-credentials" not in response.headers


def test_the_default_origin_is_the_dev_server_only():
    """Production overrides this from the instance environment. The default exists so a fresh
    checkout works, and must not quietly become a wildcard."""
    assert get_settings().cors_allow_origins == [ALLOWED]
