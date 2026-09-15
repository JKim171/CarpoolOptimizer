"""Everything that stands between the database and the pure domain (docs/design.md 4.1).

`packages/domain` performs no I/O: it takes a `ProblemInstance` and returns a `Solution`, knowing
nothing about tables, sessions, clocks or providers. That rule is what lets the API, the worker and
the benchmark harness import the same solver -- and this package is where the cost of it is paid.

Four translations happen here, and each one is a place a unit mismatch could quietly wreck a result:

* **Identity.** Participant UUIDs become the domain's opaque string node ids.
* **Time.** `timestamptz` columns become epoch seconds; `max_detour_minutes` becomes seconds.
* **Distance and duration.** A routing provider (haversine until Week 4) becomes a `TravelMatrix`.
* **Vocabulary.** A `validate.Constraint` becomes the string `unassigned_participants.reason` has.

Nothing in here belongs in `packages/domain`, and nothing in `packages/domain` should need changing
to add a provider.
"""
