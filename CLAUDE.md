# CarpoolOptimizer — working notes

Carpool optimization for events: an organizer enters a roster, the system decides who drives whom,
in what pickup order, out and back.

Design lives in [`docs/design.md`](docs/design.md); the delivery plan in
[`docs/roadmap.md`](docs/roadmap.md). Read those before proposing architectural changes — most
decisions already have a recorded reason.

## Hard rules

### Never write secrets outside `.env`

**This repository is public.** Anything committed is public permanently — force-pushing does not
undo it, bots scrape new commits within minutes, and the only real remediation is rotating the
credential.

- Credentials, API keys, tokens, connection strings, and signing secrets go in `.env` /
  `.env.local`, which are gitignored. Nowhere else — not in source, not in tests, not in
  `docker-compose.yml`, not in CI workflow files, not in a comment "temporarily".
- Commit an `.env.example` with **placeholder** values when documenting a new variable.
- Real values in CI come from GitHub Actions secrets; in production from the host's environment.
- Local development credentials in `docker-compose.yml` (e.g. `POSTGRES_PASSWORD: carpool`) are
  deliberate throwaways for a container bound to localhost. Never reuse that pattern for anything
  reachable from outside the machine.

GitHub secret scanning and push protection are enabled and will block a push containing a detected
credential. Treat that as a backstop, not a safety net — it does not recognize every format.

### Never commit real participant data

The database holds people's home addresses, and the product is aimed at groups that may include
minors (`docs/design.md` §2, §5.3.2). A roster pasted into a fixture or a debugging dump committed
"just for a second" is a privacy incident, not an embarrassment.

- Test fixtures and seed data are **generated**, never dumped from a real event. The synthetic
  instance generator exists so this is never necessary.
- Backups go to object storage, never to git.

### `packages/domain` performs no I/O

No database, no HTTP, no clock, no filesystem. It takes a `ProblemInstance` and returns a
`Solution`. This is what lets the API, the worker, and the benchmark harness import the same solver,
and what keeps solver tests fast and deterministic (`docs/design.md` §4.1). Anything needing I/O
belongs in `adapters/`.

## Commands

```sh
make setup     # venv + dev dependencies + editable install
make check     # ruff, ruff format --check, mypy (strict), pytest
make test      # pytest only
make fmt       # ruff format + ruff check --fix
make db        # postgres + postgis via docker compose
```

`make check` must pass before a commit. CI runs the same steps.

## Layout

```
packages/domain/   pure optimization domain — models, objective, feasibility validation
apps/web/          Next.js frontend (not yet started)
docs/              design document and roadmap
```

## Conventions

- Durations are integer **seconds**; times are **epoch seconds**. One unit throughout is what keeps
  the objective weights interpretable (a `vehicle` weight of 600 means one fewer car is worth ten
  minutes of driving).
- Routes store orderings, not schedules. Times are derived so a route survives a matrix refresh.
- Solvers may be heuristic about quality, never about feasibility — every solver's output must pass
  `validate()`.
- `Role.EITHER` is **dormant by decision, not dead code.** It is fully implemented and tested, but
  the MVP roster UI does not offer it (`docs/design.md` §2.3). Do not remove it for being unused.
  Note that while it stays unsurfaced, the driver set is fixed and the `vehicle` objective weight
  has no effect on any result.
