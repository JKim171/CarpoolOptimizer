# CarpoolOptimizer — 6-Week Delivery Plan

**Start:** 2026-09-08 · **Presentable by:** ~2026-10-20
**Assumed capacity:** ~12 focused hours/week (~72 hours total)
**First real users:** campus club tennis (the author coordinates it) · **Then:** a public US site
**Budget:** ~$1/month while AWS credits last (~11 months), ~$18.50/month after (less with a
Savings Plan)

See `design.md` for architecture, schema, API, and optimization design.

---

## What "presentable in 6 weeks" means

Four things, in priority order. If time runs out, it runs out from the bottom.

1. **Deployed and working at a real URL**, used by a real club tennis practice.
2. **A benchmark table with real numbers** — the evidence for how good the solvers are.
3. **A README a newcomer can understand in 90 seconds** — architecture diagram, benchmark
   table, 20-second demo GIF, honest "what's real vs. synthetic" section.
4. Infrastructure depth: the `SKIP LOCKED` queue, idempotency, concurrency guards.

Note that #3 is the one most often skipped, and the one that determines whether anyone besides the
author can understand the work. Week 6 is reserved for it and should not be raided.

---

## Week 1 — Foundations and the domain core

No web layer at all this week. The solver ships before the API.

- Monorepo skeleton: `apps/api`, `apps/web`, `packages/domain`.
- `docker compose`: postgres+postgis, osrm (regional extract), api.
- Alembic baseline migration; Ruff + mypy + pytest in GitHub Actions; `/healthz`.
- `packages/domain`: `ProblemInstance` / `Solution` dataclasses, objective function (§8.1),
  **Held–Karp exact sequencing** for ≤8 stops, **greedy insertion** assignment.
- Feasibility validator; synthetic instance generator (uniform / clustered / radial).
- Hypothesis property tests: every solution satisfies capacity, time windows, detour caps,
  exactly-once assignment.

**Done when:** you can solve a 200-participant synthetic instance from a Python REPL, and the
validator confirms feasibility. CI is green.

**Status (2026-09-10): met.** The domain core, validator, generator, property tests, and CI are
built — 1,000 participants solve greedily in 0.2 s. Carried forward: the `apps/api` skeleton,
Alembic baseline, and `/healthz` move to Week 2, where they belong with the API; OSRM in compose
moves to Week 5, the only week that needs it.

---

## Week 2 — Backend API (organizer-entered roster)

Model A only (`design.md` §2.1): the coordinator enters the whole roster. This removes the join
flow, participant tokens, and redaction from the critical path — real usage arrives a week sooner.

- `apps/api` skeleton, Alembic baseline, `/healthz` (carried from Week 1). `.env.example` with a
  placeholder `ORS_API_KEY`.
- Replace the amd64-only `postgis/postgis` image with one built `FROM postgres:16` plus Debian's
  PostGIS package, so development (Apple Silicon) and production (Graviton) both run it natively
  (`design.md` §10.1).
- Domain first: `ProblemInstance` gains the event end time, so return-leg drop-off ETAs can be
  scheduled forward from it (the forward scheduler already exists).
- Full schema from `design.md` §5, including `participants_version`, `input_fingerprint`, `priority`,
  `geocode_source`, and the TTL'd `geocode_cache` (§5.2),
  `pinned_driver_id`, and both partial unique indexes (painful to retrofit once there is live data).
  Also `events.ends_at` and `route_stops.leg`, which the return leg needs.
- Event / participant / job / solution endpoints per §6, organizer principal only. The
  50-participant cap enforced in the API, race-free (`design.md` §5.1).
- Optimization runs **inline (synchronous)** — but behind the async contract:
  `POST → 202 {job_id}` and `GET /v1/optimizations/{job_id}`. Week 4 swaps the executor only; the
  API contract and the frontend do not move.
- Round-trip solve: outbound and return legs sequenced independently (§8.2).
- testcontainers integration tests against real Postgres.

**Done when:** create event → add roster → optimize → fetch routes works end-to-end via `curl`,
with both legs returned.

### Parallel track, weeks 2–3 — infrastructure (`design.md` §10.1)

Independent of the API, so it runs alongside it and is ready for the Week 3 deploy.

- Billing guardrails and IAM Identity Center (SSO) for the developer — before any resource exists.
- Terraform, state in an S3 backend; `*.tfstate*` and `.terraform/` gitignored first.
- VPC with one public subnet, internet gateway, route table. No NAT gateway.
- EC2 `t4g.small`, 20 GB gp3, security group allowing 80/443 only, SSM Session Manager in place of
  SSH, Docker installed through user data, a swap file.
- IAM instance role scoped to the backup bucket; S3 backup bucket with versioning and a lifecycle
  rule.
- GitHub Actions OIDC provider and a deploy role scoped to this repository.
- CloudWatch alarms: status check failure, CPU credit balance, disk usage.

**Done when:** `terraform apply` from nothing yields an instance you can open a shell on through
SSM, with no SSH port open and no AWS access key anywhere; `terraform destroy` removes all of it.

---

## Week 3 — Coordinator UI, deploy, and the first real event

The most important week in the plan.

- Next.js. Three screens: create event · roster table (fast bulk entry — name, pickup, driver?,
  seats, priority) · results view with MapLibre routes and a per-driver pickup/dropoff order.
- Roster offers two roles only, driving or needs-a-ride. Flexible drivers stay unsurfaced for the
  first real event (`design.md` §2.3).
- Roster entry is the whole UX problem here. It must be faster than the spreadsheet the coordinator
  uses today, or they will keep using the spreadsheet. Paste-from-clipboard is worth an hour.
- Results show both legs: pickup order out, drop-off order back, and an "Open in Google Maps" link
  per leg (`design.md` §7.3).
- Manual pin + re-optimize, so the coordinator can override the solver and keep going.
- Job status polling via TanStack Query.
- Deploy: Vercel (web) + the Terraform-built EC2 instance running Caddy, api, and Postgres under
  Docker Compose (`design.md` §10.1), deployed by GitHub Actions through OIDC. Production compose
  publishes no database port. Real domain, HTTPS.
- Nightly `pg_dump` to S3 through the instance role **before** the first real event — with
  Postgres self-hosted it is the only copy of the data.
- **Run one real club tennis practice through it.**

**Done when:** real people got real assignments and drove to real practice. Then write down what
broke — that list drives weeks 4–6 more reliably than this plan does.

> The author is the coordinator, so this cannot be a usability test of the coordinator. Watch the
> drivers and riders instead — the people who did not design it — and, before the public launch,
> hand it to one organizer from outside the club. Do not help. Watch where they hesitate.

---

## Week 4 — Async infrastructure and the recurring-event loop

- `SKIP LOCKED` job queue with lease-based visibility timeout (§4.2). **Decide first** whether the
  worker is a separate process or an in-process background task, against the triggers in
  `design.md` §4.2 — multi-second LNS budgets, solves lost to deploys, or ORS failures reaching
  users. The instance can run either; the claim/lease code is the same.
- Bounded retries, expired-lease reclaim, cooperative cancellation, progress checkpointing.
- `input_fingerprint` dedup; `participants_version` staleness detection with auto-requeue.
- ORS behind the routing interface (`design.md` §4.4): one matrix request per solve, Directions
  fetched lazily per route, geocoding proxied through the API. The saved 51-point playground
  response makes a parsing fixture — random points, no key, so safe to commit. `travel_cache` with
  hit-rate metrics.
- **Churn-penalized re-optimization** (`w6`) — makes it usable week over week.
- **Clone-last-week / roster reuse** (§5.3) — the thing club tennis will actually ask for. Copies
  participant rows forward; the canonical `people` address book waits for accounts.
- *If ahead of schedule:* Model B — the self-service join link, participant tokens, and redaction
  (§6.1–6.2). Otherwise this is the first post-launch feature.

**Done when:** killing the worker mid-job results in the job completing correctly on reclaim,
exactly once in effect; and re-optimizing a changed event preserves most prior assignments.

---

## Week 5 — Algorithms and benchmarks

The algorithmic core. Protect this week.

- **CP-SAT exact model** (OR-Tools) — proves optimality for n ≲ 40 and yields the optimality gap.
  Benchmark-only: OR-Tools is a benchmark dependency and never ships in the production image
  (`design.md` §8.3).
- OSRM in compose with a single-state extract (carried from Week 1) — the whole-US extract is too
  large for a laptop, and the benchmarks do not need it.
- **LNS**: ruin-and-recreate, relocate / swap / 2-opt, simulated-annealing acceptance.
- Benchmark harness: n ∈ {20, 50, 100, 250, 500, 1000} × driver ratio ∈ {0.2, 0.35, 0.5} × three
  spatial distributions, fixed seeds, against local OSRM. Results committed as JSON.
- Charts rendered from that JSON.
- Small benchmark subset as a **CI regression gate** — quality degradation fails the build.
- *Stretch:* min-cost flow relaxation as a lower bound and warm start.

**Done when:** the benchmark table exists with numbers you can defend, including a measured gap to
proven optimal on the instances CP-SAT can close.

---

## Week 6 — Hardening and packaging

- structlog JSON logging with job correlation ids; Sentry; solve-time histograms by algorithm and n.
- Rate limiting on join and optimize endpoints, plus a per-event daily solve limit — a
  prerequisite for public launch, not polish (`design.md` §2.4).
- Rehearse one restore from the S3 backups.
- Organizer email on event creation (Resend free tier) so the organizer token isn't lost.
- Error states, empty states, "no feasible solution" explanations in the UI.
- **README**: architecture diagram, benchmark table, 20-second demo GIF, design-decision rationale,
  and an explicit *"real usage vs. synthetic benchmarks"* section.
- Collect real metrics: events run, participants, completion rate, solve times, cache hit rate.

**Done when:** someone who has never seen the project understands what it does and why it's hard,
within 90 seconds of opening the README.

---

## Cut list — explicitly not in the 6 weeks

Redis · Celery · SSE/WebSockets · user accounts · SMS · ECS · OR-Tools Routing solver ·
calendar integration · analytics dashboard · PWA. Self-service join links (Model B) are week 4 only
if weeks 1–3 run ahead; otherwise they are the first post-launch feature.

Round-trip routing is **no longer** on this list — the return leg is in scope from week 2, because
the driver getting home easily is a stated requirement, and a detour measured on the outbound leg
alone understates the real burden by roughly 2x.

Each has a documented trigger condition in `design.md` §10. None of them is on the critical path to a
deployed, benchmarked, actually-used product.

## Before opening to the public — gates, not weeks

Club tennis needs none of these, because its coordinator enters the roster. A public site where
strangers create events needs all of them (`design.md` §2.4):

- Self-service join links (Model B) — organizers rarely know every participant's address.
- Rate limits and per-event solve limits — the ORS quotas are one pool shared by every user.
- Retention policy, a privacy page, and event deletion.
- ORS (and geocoder) terms confirmed for a free public website.

---

## If you fall behind

Drop in this order — first to go at the top:

1. Min-cost flow bound (stretch already)
1b. Model B join links (already conditional)
2. Email (organizer token can live in a cookie plus the share link)
3. `travel_cache` (small events tolerate direct API calls)
4. Cooperative cancellation
5. Churn penalty — painful to lose, but the product survives without it

**Never drop:** the deployed real event (W3), CP-SAT + LNS + benchmarks (W5), or the README (W6).
Those three are the core of the project: real use, measured quality, and a clear explanation.

---

## Cost model

| Item | Tier | Monthly |
|---|---|---|
| Vercel | Hobby (non-commercial) — frontend | $0 |
| **AWS EC2 `t4g.small`** | 2 vCPU (Graviton) / 2 GB, `us-east-1`. Docker Compose: Caddy + api + worker + Postgres | **$12.26** |
| EBS gp3 | 20 GB | $1.60 |
| Public IPv4 | One address | $3.65 |
| Data transfer out | Under the 100 GB/month free allowance | $0 |
| S3 | Terraform state + nightly backups, a few MB | ~$0.05 |
| CloudWatch | A handful of alarms, within the free tier | $0 |
| Postgres + PostGIS | Self-hosted on the instance | $0 |
| Routing, directions, geocoding | ORS free Standard plan | $0 |
| Sentry | Developer free | $0 |
| OSRM | Local Docker only — never deployed | $0 |
| Domain | GitHub Student Pack: free first year — check the renewal price before choosing | $0 → ~$1 |
| **Total** | AWS lines covered by credits (up to $200, 12 months) for ~11 months | **~$1/month on credits; ~$18.50/month after** |

Hosts considered, verified 2026-09-10 — all run the same `docker compose up`:

| Option | Specs | Monthly | Outcome |
|---|---|---|---|
| **AWS EC2 `t4g.small`** | 2 vCPU Graviton / 2 GB | ~$17.50 all-in | **Chosen.** Instance role, SSM, and OIDC mean no long-lived AWS credential exists anywhere; Terraform makes it reproducible (`design.md` §10.1). Matches the arm64 dev machine. |
| AWS EC2 `t3.small` | 2 vCPU x86 / 2 GB | ~$20.40 all-in | Same, ~$3 more, and emulated relative to the dev machine. |
| AWS Lightsail | 2 vCPU / 2 GB / 60 GB, IPv4 | $12 flat | Chosen first, superseded the same day: simpler and cheaper, but its instances cannot assume IAM roles, so S3 backups would need a stored access key, and shell access means an open SSH port. The fallback if the infrastructure track stalls. |
| Hetzner Cloud | Cost-optimized line | from $7.09 | Sold out. |
| Hetzner Cloud | Regular performance | from $14.09 | More expensive, no credits, same stored-key problem for backups. |
| Neon (database) | Free plan: 100 CU-hours/month | $0 | Rejected: a polling worker needs ~183 (`design.md` §10.1). |
| Oracle Cloud Always Free | 4 ARM cores / 24 GB | $0 | Reclaims idle instances — and this one is idle nearly always. |
| Home server | — | ~$0 | Possible later behind Cloudflare Tunnel (no open ports, hidden IP); costs uptime. |

Instance prices are on-demand us-east-1 from a third-party price tracker; EBS and IPv4 are AWS's
published rates. Re-check in the AWS Pricing Calculator before relying on them.

Running api and worker as two processes on one machine (rather than two machines) is a deliberate
budget choice for v1 — see `design.md` §10.1. They remain genuinely separate processes with a real
queue between them, so splitting them out later is a deploy config change, not a refactor.

Billing guardrails, set before anything is created: a zero-spend budget (alerts on any cost the
credits do not cover) and a $15 monthly cost budget that **excludes credits**, with actual and
forecast alerts, so a forgotten resource quietly burning credits is still visible. MFA on the root
user. No long-lived AWS access keys: Terraform runs on short-lived SSO sessions, CI on OIDC, the
instance on its role. AWS has no hard spending cap on a paid account, and EC2 — unlike Lightsail —
is not flat-rate, so the budgets matter more here; Terraform keeps every billable resource declared
and visible in `plan`.

---

## Risks

| Risk | Mitigation |
|---|---|
| Club tennis doesn't adopt it | Reduced: the author is the coordinator. The remaining risk is the opposite — building for one coordinator's habits. Watch drivers and riders in week 3, and one outside organizer before the public launch. |
| Geocoding terms forbid storing coordinates permanently | **Resolved by design** — addresses are the durable record, coordinates are TTL-cached (`design.md` §5.2). Provider choice is now reversible. |
| Host cannot run an always-on worker on a cheap tier | **Resolved** — an EC2 instance runs whatever is started on it (`design.md` §10.1). |
| PostGIS unavailable on the free tier | **Moot** — Postgres is self-hosted with PostGIS in the image. |
| Self-hosted Postgres loses data | Nightly `pg_dump` to versioned S3 from before the first real event; one rehearsed restore in week 6. |
| One client exhausts the shared ORS quota on the public site | Per-event and per-client limits; haversine fallback when quota runs out (`design.md` §2.4). |
| The infrastructure track eats Week 3 | Start it in Week 2, in parallel with the API. Fallback: Lightsail runs the same compose file — an afternoon, not a redesign. |
| Terraform state committed to this public repo | S3 backend and `.gitignore` entries exist before the first `terraform init`. |
| A forgotten EC2-adjacent resource bills quietly (NAT gateway, unattached IP, snapshots) | Everything through Terraform; the credits-excluded budget surfaces burn the zero-spend budget cannot see. |
| OSRM regional extract setup eats a day | Timebox to 3 hours; haversine × road-factor is an acceptable benchmark stand-in. |
| Weeks 5–6 get squeezed | Weeks 1–4 have explicit cut items; weeks 5–6 do not. Protect them. |

---

## Project summary — fill in at the end, from real numbers

Do not write this now. Write it in week 6 from measured data, for the top of the README.

> CarpoolOptimizer has coordinated **N** real events and **M** participants. Its
> large-neighborhood-search solver lands within **X%** of CP-SAT-proven optimal and handles
> 1,000 participants in **Y** seconds, on a Postgres `SKIP LOCKED` job queue with lease-based
> failure recovery and fingerprint-based idempotency.

Every placeholder is something this plan actually produces. Keep the distinction between real
usage (N, M) and synthetic benchmarks (X, Y) explicit — in the README and anywhere else the
numbers are quoted.
