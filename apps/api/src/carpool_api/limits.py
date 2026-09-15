"""Product limits enforced by the API.

These live here, and never in `packages/domain` (CLAUDE.md): the solver is the same code the
benchmark harness runs at n = 1000, so a cap compiled into it would make the benchmark impossible.
"""

from __future__ import annotations

#: Active participants per event (docs/design.md 2.4, 5.1).
#:
#: Sized by the matrix request it implies, not chosen for roundness: 50 participants plus the shared
#: destination is 51 nodes, and 51 x 51 = 2,601 cells fits openrouteservice's documented 3,500-cell
#: limit in a single request. One request means no tiling, no stitching, and no partial-failure
#: handling in the routing adapter. Raising this number is a routing-adapter decision, not a
#: validation tweak.
MAX_ACTIVE_PARTICIPANTS = 50
