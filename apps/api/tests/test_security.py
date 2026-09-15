"""Handles, tokens, and the one coordinate ordering that must never drift."""

import hashlib
import re

from carpool_api.geo import point
from carpool_api.security import (
    PUBLIC_ID_ALPHABET,
    PUBLIC_ID_LENGTH,
    hash_token,
    new_public_id,
    new_token,
)


def test_public_ids_avoid_look_alike_characters():
    """A handle gets typed off a screen, so 0/o and 1/l must not both be possible."""
    assert not set("01ilo") & set(PUBLIC_ID_ALPHABET)


def test_public_id_has_the_declared_shape():
    for _ in range(50):
        public_id = new_public_id()
        assert len(public_id) == PUBLIC_ID_LENGTH
        assert set(public_id) <= set(PUBLIC_ID_ALPHABET)


def test_public_ids_do_not_repeat():
    assert len({new_public_id() for _ in range(500)}) == 500


def test_tokens_are_url_safe_and_unique():
    """The token travels in a link, so anything needing percent-encoding is a bug."""
    tokens = {new_token() for _ in range(200)}

    assert len(tokens) == 200
    assert all(re.fullmatch(r"[A-Za-z0-9_-]+", token) for token in tokens)


def test_hash_token_is_sha256_of_the_utf8_bytes():
    """Pinned because the digest is a storage format: changing it invalidates every live token."""
    assert hash_token("hunter2") == hashlib.sha256(b"hunter2").digest()
    assert len(hash_token(new_token())) == 32


def test_point_writes_longitude_first():
    """WKT is `POINT(x y)` -- longitude then latitude -- while this API's JSON is latitude first.

    Deliberately asymmetric numbers: with lat and lng both positive and similar, a swap would still
    produce a valid point somewhere plausible and no test would notice.
    """
    assert point(42.2808, -83.7430).data == "POINT(-83.743 42.2808)"


def test_point_carries_wgs84():
    assert point(42.2808, -83.7430).srid == 4326
