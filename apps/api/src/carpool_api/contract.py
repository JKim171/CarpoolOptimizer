"""Emit the OpenAPI document as a stable file.

The web client's TypeScript types are generated from this file rather than hand-written, so that a
change to a response model cannot silently leave the frontend believing in a field that no longer
exists. The same reasoning as the migration drift test: the contract has one source of truth --
here, the Pydantic schemas -- and everything downstream is generated from it and checked.

Two links in that chain, each with its own check:

    Pydantic schemas  ->  apps/web/lib/api/openapi.json  ->  apps/web/lib/api/schema.d.ts
                      ^                                  ^
                      test_openapi_contract.py           npm run types:check

`make openapi` regenerates both. Nothing here touches a database.

Usage: python -m carpool_api.contract [path]   (stdout when no path is given)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def openapi_document() -> dict[str, Any]:
    """The schema FastAPI would serve at `/openapi.json`."""
    from carpool_api.main import create_app

    return create_app().openapi()


def serialize(document: dict[str, Any]) -> str:
    """Render the document so that an unchanged schema produces a byte-identical file.

    `sort_keys` is what makes that true: FastAPI builds the schema by walking routes and models, and
    a reordering there would otherwise show up as a diff in a file nobody edited.
    """
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    text = serialize(openapi_document())
    if argv:
        Path(argv[0]).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
