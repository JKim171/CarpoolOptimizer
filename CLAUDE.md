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
  deliberate throwaways, and they are only acceptable because the port is published to
  **`127.0.0.1` explicitly**. That binding is what makes the rest of this bullet true, so it is
  load-bearing, not cosmetic: a bare `5432:5432` binds `0.0.0.0` and `[::]` and puts a Postgres
  **superuser**, whose password is published in this public repository, on every network the
  machine joins. Docker publishes ports through its own forwarding rules, which bypass the host
  firewall. Never reuse that pattern for anything reachable from outside the machine, and never
  drop the `127.0.0.1:` prefix from a published port.

- Terraform state (`*.tfstate*`, `.terraform/`) is never committed — it can hold secrets in plain
  text. It lives in the S3 backend.
- No long-lived AWS access keys, anywhere: the developer uses SSO sessions, CI uses OIDC, the
  instance uses its IAM role.

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
make setup     # venv + dev dependencies + editable install, and npm ci for the web app
make check     # ruff, ruff format --check, mypy (strict), pytest, then the web checks
make test      # pytest only
make fmt       # ruff format + ruff check --fix
make db        # postgres + postgis via docker compose
make api       # uvicorn on :8000
make web       # next dev on :3000
make openapi   # regenerate the API contract and the TypeScript types built from it
```

`make check` must pass before a commit. CI runs the same steps, in two jobs (`check` and `web`).

**The API contract is generated, not hand-written.** `apps/web/lib/api/schema.d.ts` comes from
`apps/web/lib/api/openapi.json`, which comes from the Pydantic schemas. Change a route or a model
and `make openapi`, or `test_openapi_contract.py` fails the build — the same guard as the migration
drift test, one layer out. Never edit either generated file by hand.

Commits use [Conventional Commits](https://www.conventionalcommits.org/): `feat(domain): …`,
`fix(api): …`, `docs: …`. The two plain-subject commits early in the history predate this.

Commits and pull requests **name a single author**: no `Co-Authored-By:` trailer and no
"generated with" line, in a commit message or a PR description. Some tooling appends these by
default; this rule overrides that default.

`.githooks/commit-msg` enforces it, so a stray trailer fails the commit rather than being noticed
later. `.git/hooks` is not committed, so the hook lives in `.githooks/` and `make setup` points
`core.hooksPath` at it — after a fresh clone, run `make setup` (or
`git config core.hooksPath .githooks`) or the hook is not active.

## Layout

```
packages/domain/   pure optimization domain — models, objective, feasibility validation
apps/api/          FastAPI service — schema, endpoints, the DB↔domain adapter
apps/web/          Next.js frontend (App Router, TypeScript strict)
infra/             Terraform — VPC, instance, buckets, IAM, alarms
docs/              design document and roadmap
```

Nothing with the `NEXT_PUBLIC_` prefix is a secret: Next compiles those values into the browser
bundle. The ORS key in particular stays on the API, which is why geocoding is proxied rather than
called from the browser (`docs/design.md` §4.4).

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
