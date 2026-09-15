"""Public handles and bearer tokens (docs/design.md 6.1).

There are no passwords and no OAuth. Access to an event is held by an opaque token, of which the
database stores only a SHA-256 digest -- so a database dump does not hand over event control.

Two kinds of random string are generated here and they are not interchangeable:

* `new_public_id()` is a **handle**, not a secret. It appears in URLs and is safe to log. It is
  random only so that event ids are not enumerable.
* `new_token()` is a **credential**. It is shown once, at creation, and is never recoverable
  afterwards -- only its digest is kept.

A bare SHA-256 is the right hash here, where it would be indefensible for a password: the input is
256 bits of `secrets` entropy, so there is no dictionary to attack and nothing for a slow KDF to
protect. Lookup is an indexed equality on the digest, which is also why no constant-time comparison
appears in this codebase.
"""

from __future__ import annotations

import hashlib
import secrets

#: Digits and lowercase letters, minus `0`/`o`, `1`/`l` and `i` -- a handle gets read aloud and
#: typed off a screen, so look-alikes cost more than the four characters of alphabet they add.
PUBLIC_ID_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
PUBLIC_ID_LENGTH = 10

#: 256 bits, URL-safe base64 encoded, because the token travels in a link.
TOKEN_BYTES = 32


def new_public_id() -> str:
    """An unguessable, non-secret handle for an event."""
    return "".join(secrets.choice(PUBLIC_ID_ALPHABET) for _ in range(PUBLIC_ID_LENGTH))


def new_token() -> str:
    """A fresh bearer token in plaintext. Return it to the caller once, then keep only the hash."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> bytes:
    """The digest stored in `event_tokens.token_hash` / `participants.token_hash`."""
    return hashlib.sha256(token.encode()).digest()
