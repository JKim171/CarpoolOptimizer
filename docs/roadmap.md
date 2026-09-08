# CarpoolOptimizer — 6-Week Delivery Plan

**Start:** 2026-09-08 · **Presentable by:** ~2026-10-20
**Assumed capacity:** ~12 focused hours/week (~72 hours total)
**First real users:** campus club tennis · **Budget target:** ~$0–10/month

See `design.md` for architecture, schema, API, and optimization design.

---

## What "presentable in 6 weeks" means

Four things, in priority order. If time runs out, it runs out from the bottom.

1. **Deployed and working at a real URL**, used by a real club tennis practice.
2. **A benchmark table with real numbers** — the algorithmic differentiator.
3. **A README that a hiring manager can skim in 90 seconds** — architecture diagram, benchmark
   table, 20-second demo GIF, honest "what's real vs. synthetic" section.
4. Infrastructure depth: the `SKIP LOCKED` queue, idempotency, concurrency guards.

Note that #3 is the one people skip and the one that actually determines whether the work reads as
impressive. Week 6 is reserved for it and should not be raided.

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

---

## Week 2 — Backend API (organizer-entered roster)

Model A only (`design.md` §2.1): the coordinator enters the whole roster. This removes the join
flow, participant tokens, and redaction from the critical path — real usage arrives a week sooner.

- Full schema from `design.md` §5, including `participants_version`, `input_fingerprint`, `priority`,
  `geocode_source`, and the TTL'd `geocode_cache` (§5.2),
  `pinned_driver_id`, and both partial unique indexes (painful to retrofit once there is live data).
- Event / participant / job / solution endpoints per §6, organizer principal only.
- Optimization runs **inline (synchronous)** — but behind the async contract:
  `POST → 202 {job_id}` and `GET /v1/optimizations/{job_id}`. Week 4 swaps the executor only; the
  API contract and the frontend do not move.
- Round-trip solve: outbound and return legs sequenced independently (§8.2).
- testcontainers integration tests against real Postgres.

**Done when:** create event → add roster → optimize → fetch routes works end-to-end via `curl`,
with both legs returned.

---

## Week 3 — Coordinator UI, deploy, and the first real event

The most important week in the plan.

- Next.js. Three screens: create event · roster table (fast bulk entry — name, pickup, driver?,
  seats, priority) · results view with MapLibre routes and a per-driver pickup/dropoff order.
- Roster offers two roles only, driving or needs-a-ride. Flexible drivers stay unsurfaced for the
  first real event (`design.md` §2.3).
- Roster entry is the whole UX problem here. It must be faster than the spreadsheet the coordinator
  uses today, or they will keep using the spreadsheet. Paste-from-clipboard is worth an hour.
- Manual pin + re-optimize, so the coordinator can override the solver and keep going.
- Job status polling via TanStack Query.
- Deploy: Vercel (web) + backend host + managed Postgres. Real domain, HTTPS.
- **Run one real club tennis practice through it.**

**Done when:** real people got real assignments and drove to real practice. Then write down what
broke — that list drives weeks 4–6 more reliably than this plan does.

> Sit with the coordinator while they use it the first time. Do not help. Watch where they hesitate.

---

## Week 4 — Async infrastructure and the recurring-event loop

- `SKIP LOCKED` job queue with lease-based visibility timeout (§4.2). Resolve the always-on-worker
  question first (§11 item 2) — in-process background task is the likely v1 answer.
- Bounded retries, expired-lease reclaim, cooperative cancellation, progress checkpointing.
- `input_fingerprint` dedup; `participants_version` staleness detection with auto-requeue.
- Real routing provider behind the interface + `travel_cache` with hit-rate metrics.
- **Churn-penalized re-optimization** (`w6`) — makes it usable week over week.
- **Clone-last-week / roster reuse** (§5.3) — the thing club tennis will actually ask for. Copies
  participant rows forward; the canonical `people` address book waits for accounts.
- *If ahead of schedule:* Model B — the self-service join link, participant tokens, and redaction
  (§6.1–6.2). Otherwise this is the first post-launch feature.

**Done when:** killing the worker mid-job results in the job completing correctly on reclaim,
exactly once in effect; and re-optimizing a changed event preserves most prior assignments.

---

## Week 5 — Algorithms and benchmarks

The differentiator. Protect this week.

- **CP-SAT exact model** (OR-Tools) — proves optimality for n ≲ 40 and yields the optimality gap.
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
- Rate limiting on join and optimize endpoints.
- Organizer email on event creation (Resend free tier) so the organizer token isn't lost.
- Error states, empty states, "no feasible solution" explanations in the UI.
- **README**: architecture diagram, benchmark table, 20-second demo GIF, design-decision rationale,
  and an explicit *"real usage vs. synthetic benchmarks"* section.
- Collect real metrics: events run, participants, completion rate, solve times, cache hit rate.

**Done when:** someone who has never seen the project understands what it does and why it's hard,
within 90 seconds of opening the README.

---

## Cut list — explicitly not in the 6 weeks

Redis · Celery · SSE/WebSockets · user accounts · SMS · AWS/Terraform · OR-Tools Routing solver ·
calendar integration · analytics dashboard · PWA. Self-service join links (Model B) are week 4 only
if weeks 1–3 run ahead; otherwise they are the first post-launch feature.

Round-trip routing is **no longer** on this list — the return leg is in scope from week 2, because
the driver getting home easily is a stated requirement, and a detour measured on the outbound leg
alone understates the real burden by roughly 2x.

Each has a documented trigger condition in `design.md` §10. None of them is on the critical path to a
deployed, benchmarked, actually-used product.

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
Those three are the entire portfolio value.

---

## Cost model

| Item | Tier | Monthly |
|---|---|---|
| Vercel | Hobby (non-commercial) — frontend | $0 |
| **Always-on VPS** | 2 vCPU / 2–4 GB, Docker Compose: Caddy + api + worker | **$4–11** |
| Neon Postgres | Free (scale-to-zero, PostGIS) | $0 |
| Routing matrix API | ORS / Mapbox free tier | $0 |
| Sentry | Developer free | $0 |
| Object storage for backups | Cloudflare R2 free tier | $0 |
| OSRM | Local Docker only — never deployed | $0 |
| Domain | — | ~$1 (≈$12/yr) |
| **Total** | | **~$5–12/month** |

VPS options, cheapest first — all run the same `docker compose up`:

| Option | Specs | ~Monthly | Note |
|---|---|---|---|
| Oracle Cloud Always Free | 4 ARM cores / 24 GB | $0 | Absurdly generous, but capacity is often unavailable and idle accounts can be reclaimed. Good home for OSRM if wanted. |
| Hetzner CX22 | 2 vCPU / 4 GB / 40 GB | ~$4 | Best price/performance. Not AWS-branded. |
| AWS Lightsail | 2 vCPU / 2 GB / 60 GB | ~$10 | AWS-branded with **fixed** billing — no surprise egress or NAT charges. |
| AWS EC2 t4g.small | 2 vCPU / 2 GB | ~$12 + EBS | Only if the EC2/VPC experience itself is the goal. |
| Fly.io | shared-cpu-1x 512 MB ×2 | ~$4–7 | Best DX; verify current pricing. |

*Verify all of these before committing — this category re-prices frequently.*

Running api and worker as two processes on one machine (rather than two machines) is a deliberate
budget choice for v1 — see `design.md` §10.1. They remain genuinely separate processes with a real
queue between them, so splitting them out later is a deploy config change, not a refactor.

On AWS specifically: single instance in a **public** subnet, Caddy for TLS. No ALB (~$16/mo), no
NAT Gateway (~$32/mo) — each costs more than the compute it would front. Set a budget alert first.

---

## Risks

| Risk | Mitigation |
|---|---|
| Club tennis doesn't adopt it | Talk to the organizer in **week 1**, not week 3. Build what they ask for. |
| Geocoding terms forbid storing coordinates permanently | **Resolved by design** — addresses are the durable record, coordinates are TTL-cached (`design.md` §5.2). Provider choice is now reversible. |
| Host cannot run an always-on worker on a cheap tier | `design.md` §11 item 2. Fallback: worker as an in-process background task. |
| OSRM regional extract setup eats a day | Timebox to 3 hours; haversine × road-factor is an acceptable benchmark stand-in. |
| Weeks 5–6 get squeezed | Weeks 1–4 have explicit cut items; weeks 5–6 do not. Protect them. |
| PostGIS unavailable on the free tier | Documented fallback in `design.md` §5. |

---

## Resume line — fill in at the end, from real numbers

Do not write this now. Write it in week 6 from measured data.

> Built and deployed a full-stack carpool optimization platform (FastAPI, Postgres/PostGIS,
> Next.js, Fly.io) used for **N** real events coordinating **M** participants. Implemented a
> large-neighborhood-search solver reaching within **X%** of CP-SAT-proven optimal while scaling to
> 1,000 participants in **Y** seconds, over a Postgres `SKIP LOCKED` job queue with lease-based
> failure recovery and fingerprint-based idempotency.

Every placeholder is something this plan actually produces. Keep the distinction between real
usage (N, M) and synthetic benchmarks (X, Y) explicit — in the README and in interviews.
