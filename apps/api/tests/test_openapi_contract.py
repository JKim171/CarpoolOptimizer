"""The committed OpenAPI file must match the app that produced it.

`apps/web/lib/api/schema.d.ts` is generated from that file, so a stale one means the frontend is
typed against an API that no longer exists -- and TypeScript would report no error, because the
types it checks against are exactly the wrong ones. This is the same guard as
`test_migrations_and_models_agree`, one layer out: models are the source of truth for the schema,
Pydantic is the source of truth for the contract, and both derived artefacts are checked rather
than trusted.
"""

import json
from pathlib import Path

from carpool_api.contract import openapi_document, serialize

CONTRACT = Path(__file__).resolve().parents[3] / "apps/web/lib/api/openapi.json"


def test_committed_openapi_matches_the_app():
    assert CONTRACT.exists(), f"{CONTRACT} is missing; run `make openapi`"

    current = serialize(openapi_document())
    committed = CONTRACT.read_text(encoding="utf-8")

    if current != committed:
        # Point at what moved rather than dumping two 100 KB strings into the failure output.
        current_paths = set(json.loads(current)["paths"])
        committed_paths = set(json.loads(committed)["paths"])
        detail = ""
        if added := current_paths - committed_paths:
            detail += f" added paths: {sorted(added)}."
        if removed := committed_paths - current_paths:
            detail += f" removed paths: {sorted(removed)}."
        raise AssertionError(
            "The committed OpenAPI contract is out of date; run `make openapi` and commit the "
            f"result.{detail}"
        )
