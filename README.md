# CarpoolOptimizer

Carpool optimization for events: an organizer enters a roster, and the system decides who drives
whom, in what pickup order, out and back.

**Status:** early construction. The optimization domain exists and is tested; the API, worker, and
web app do not yet.

## Design

- [`docs/design.md`](docs/design.md) — architecture, schema, API, optimization model
- [`docs/architecture/`](docs/architecture/) — deployment and request-flow diagrams
- [`docs/roadmap.md`](docs/roadmap.md) — 6-week delivery plan and cost model

## Quickstart

```sh
make setup     # venv + dev dependencies + editable install
make check     # lint, typecheck, tests
make db        # postgres + postgis via docker compose
```

## Layout

```
packages/domain/   pure optimization domain — no I/O, no database, no HTTP
apps/web/          Next.js frontend (not yet started)
docs/              design document and roadmap
```

`packages/domain` is deliberately free of I/O so it can be imported unchanged by the API, the
worker, and the benchmark harness, and tested without any infrastructure. See `docs/design.md` §4.1.

## The problem

Single-destination capacitated pickup routing — a Dial-a-Ride variant where every route ends at one
shared node. Route *sequencing* is solved exactly (Held–Karp over ≤8 stops); only the *assignment*
is heuristic. See `docs/design.md` §8.
