"""Address normalization.

One definition, used for two things that must agree: the `input_fingerprint` that decides whether an
event needs re-solving, and `geocode_cache.address_norm`, which is the cache's primary key
(docs/design.md 5.1, 5.2).

Deliberately conservative -- case, surrounding space and repeated whitespace only. It does **not**
expand "St" to "Street" or reorder components: that is parsing, it is locale-specific, and getting
it wrong would merge two genuinely different addresses into one cache entry and send a driver to the
wrong house. Two spellings of one place costing an extra geocode is the cheap failure; two places
sharing one coordinate is not.
"""

from __future__ import annotations


def normalize_address(address: str) -> str:
    """Casefolded, with runs of whitespace collapsed to single spaces."""
    return " ".join(address.split()).casefold()
