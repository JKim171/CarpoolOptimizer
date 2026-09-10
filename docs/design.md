# CarpoolOptimizer — Design Document

**Status:** Draft v3 · Last updated 2026-09-10
**Context:** Intended for real public deployment. See `roadmap.md` for the
time-boxed delivery plan.

---

## 1. Problem

Given a destination, an arrival time, and a set of participants — each with a pickup location, a
role (driver / passenger / either), a seat count if driving, and a time window — produce an
assignment of passengers to drivers and a pickup order for each driver, minimizing a weighted
objective over total drive time, vehicle count, passenger inconvenience, driver detour, and
unassigned participants.

This is a **single-destination capacitated pickup problem** — a special case of the Dial-a-Ride
Problem (DARP) in which every route terminates at one common node. It is NP-hard in general, but
the single-destination structure admits a decomposition that makes it tractable (see §8).

## 2. First real users: club tennis

The first deployment target is a campus club tennis team (~20–60 members, weekly recurring
practices at a fixed venue). The project's author is that team's coordinator, so product questions
about this use case are answered first-hand rather than inferred. This shapes the product more
than any abstract scaling concern:

| Property of the real use case | Design consequence |
|---|---|
| Pickup locations are a dense campus cluster; trips are 3–12 minutes | Absolute minutes saved are small. The product value is **coordination**, not mileage. Do not oversell distance savings. |
| Binding constraint is seats vs. riders, not routing | Feasibility and capacity handling matter more than route optimality. |
| Parking at the venue is scarce | `minimize vehicle count` is a genuinely valuable objective term, not a synthetic one. Weight it high by default. |
| Same roster, every week | **Recurring events and roster reuse are core, not "future work."** Clone-last-week must exist early. |
| Coordination happens in GroupMe on phones | Mobile-first. Join flow must complete in <30s on a phone with no account. |
| Members are students | No passwords, no OAuth. Link-based access only. |
| The coordinator already holds the roster and decides ride priority by seniority | **The organizer can enter every participant directly.** Self-service joining is a scaling feature, not a prerequisite. See §2.1. |

### 2.1 Two participation models

The system supports two ways participant data arrives. They share one schema and one API — the
difference is only *which principal* creates the `participants` rows.

**Model A — organizer-entered roster.** The coordinator types in names, pickup locations, who is
driving, and seats per car, then optimizes. This is how club tennis works today: the coordinator
already has the roster and already decides ride priority.

**Model B — self-service join link.** The organizer shares a link; participants enter their own
details. This is the scaling path — it is what makes the system a platform rather than a
coordinator's tool, and it is where the interesting authorization and privacy work lives (§6.1,
§6.2).

**Model A is a strict subset of Model B.** Identical tables; `POST /v1/events/{id}/participants`
called by an organizer principal instead of a join-token principal. So Model A ships first, reaches
real usage sooner, and Model B is additive rather than a rewrite. Do not build A as a throwaway.

### 2.2 Priority stays out of the optimizer

Club tennis allocates scarce seats by seniority. Encoding "seniority" would be wrong — it does not
generalize to weddings, conferences, or hiking trips.

Instead the model carries a **generic per-participant `priority` weight** that scales that
participant's contribution to the unassigned penalty `w5` (§8.1). Higher priority ⇒ more expensive to
leave without a ride. A coordinator expresses seniority by setting priority; another organizer might
express "has no other way to get there." The optimizer never learns why.

Alongside it, **manual pins** (`pinned_driver_id`) let an organizer force a specific assignment and
re-optimize around it. Pins are how a human overrides the solver without abandoning it — which is
what makes an optimizer usable by people who have their own reasons.

### 2.3 Flexible drivers: built, deliberately not surfaced

`Role.EITHER` -- someone who has a car but is willing to leave it at home -- is implemented,
tested, and exercised by the property suite. **The MVP roster UI does not offer it.** Participants
are either driving or need a ride, so the branch never executes at a real event yet.

**Do not delete it as dead code.** It is dormant by decision, not by neglect.

The decision it encodes is *who chooses how many cars go*:

- **Coordinator chooses** (v1): they enter exactly who is driving. The system seats everyone into
  those cars. Simple, and matches how club tennis works today.
- **System chooses** (deferred): they enter everyone who *has* a car, and the system reports the
  minimum number needed and which ones. Strictly more useful at a parking-constrained venue.

A consequence worth knowing, because it is easy to miss: **with a fixed driver set, `w2` (vehicle
count) is inert.** The number of cars is constant, so nothing the optimizer does can change it, and
the whole parking argument for weighting `w2` highly (§2) only pays off once flexible drivers
exist. Until then `w2` can be near zero without changing any result.

**Trigger to surface it:** the coordinator, having seen a real run, answers yes to "would it help
if the system told you the fewest cars you need?" The change is then one checkbox on the roster --
"must drive" versus "can drive if needed" -- against code that already works.

### 2.4 Beyond club tennis: a public product

Club tennis is the first user, not the only one. The goal is a public website any organizer in the
**United States** can use. Decided 2026-09-10:

| Decision | Reason |
|---|---|
| **At most 50 active participants per event** | 50 people + the destination is a 51 × 51 matrix — 2,601 entries, inside the routing provider's 3,500-per-request limit (§4.4), so every event is one matrix call and no tiling logic exists. The largest square that fits is 59 × 59; raising the cap past 58 brings tiling back. Enforced in the API (§5.1), **never** in `domain/` — the benchmark harness runs the same solver at n = 1000. |
| **US only (v1)** | One hosting region (US East) serves the whole country at acceptable latency; every event already carries its own IANA `timezone`. |
| **Return trip in v1; a car keeps the same riders both ways** | Matches how practices work, and is what `domain/` already implements (§8.2). Assigning the return leg separately — a rider leaving early with a different car — would turn it into a second assignment problem with per-person departure times. Not planned. |
| **Exact pickup addresses by default** | `pickup_precision` defaults to `exact`; visibility is limited by §6.2, not by blurring the data. |

Opening the site to strangers changes what "launch-ready" means. These are **prerequisites for
public launch**, not polish — none is needed for club tennis, whose roster the coordinator enters:

- **Self-service join links (Model B, §2.1).** Model A assumes the organizer knows everyone's
  address. True for a coordinator; not for a stranger organizing a wedding.
- **Rate limits and per-event solve limits.** Without accounts, anyone can create events. The
  routing and geocoding quotas (§4.4) are one pool shared by every user, so one abusive client
  exhausting them is a routing outage for everyone. The 50 cap bounds per-event cost; rate limits
  bound per-client cost; haversine is the fallback when quota runs out.
- **Retention policy, a privacy page, and event deletion.** §5.3.2 defers retention until the
  address book exists; a public site holding strangers' home addresses cannot wait that long.
- **Provider terms** confirmed to permit a free public website, not only personal/development use.

### Honest framing

At n ≈ 40 in a dense cluster, an exact solver runs in well under a second. The async job
infrastructure in this design is **not** justified by solver runtime. It is justified by travel
matrix construction against a rate-limited external routing provider, and by the need for durable,
retryable, idempotent job semantics when a solve is triggered from a phone on campus wifi. Claiming
otherwise would be inaccurate. §4.2 lists the specific failure modes.

Large-scale numbers (n = 1000) in this project come from **synthetic benchmarks**, and must always
be described as such.

## 3. Non-goals

Explicitly out of scope, with reasons:

- **Microservices, Kubernetes, Kafka, gRPC, GraphQL, event sourcing** — no load or team-topology
  justification exists at this scale. A modular monolith plus worker processes is correct here.
- **SMS notifications** — A2P 10DLC registration is weeks of compliance work.
- **Payments / cost splitting** — touches TNC regulation.
- **Multiple destinations per event** — destroys the structural property that makes §8 work.
- **Separate return-leg assignment** — riders go home in the car they came in (§2.4). The return
  leg *is* in v1; only reassigning it independently is out.
- **Events over 50 participants** — the cap keeps every event to a single matrix request (§2.4).
- **Regions outside the US (v1)** — one hosting region, one routing and geocoding configuration.

---

## 4. Architecture

```
┌────────────────────────────────────────────────────────┐
│  Next.js (Vercel free tier) — mobile-first UI, MapLibre │
└──────────────────────┬─────────────────────────────────┘
                       │ REST/JSON  (+ polling; SSE later)
┌──────────────────────▼─────────────────────────────────┐
│  FastAPI — modular monolith (AWS EC2, 1 instance)       │
│  api/      events · participants · jobs · solutions     │
│  domain/   PURE. No I/O. Solver + objective + validator │
│  adapters/ routing provider · mail · clock              │
└──────┬──────────────────────────────────┬──────────────┘
       │                                  │
┌──────▼────────────────────┐   ┌─────────▼──────────────┐
│ Postgres + PostGIS        │   │ Routing provider (iface)│
│ (container, same instance)│   │  · OSRM local (bench)   │
│  · domain tables          │   │  · ORS (prod)           │
│  · job queue (SKIP LOCKED)│   │  · haversine (fallback) │
│  · travel_cache           │   │                         │
└──────▲────────────────────┘   └────────────────────────┘
       │
┌──────┴──────────────────────────┐
│ Worker process (same image,     │
│ different entrypoint)           │
│  matrix builder → solver        │
└─────────────────────────────────┘
```

### 4.1 The one structural rule

**`domain/` is pure Python with zero I/O.** The solver accepts a `ProblemInstance` dataclass
(coordinates, capacities, time windows, a travel matrix) and returns a `Solution` dataclass. It does
not know that Postgres, HTTP, or a job queue exist.

This buys:
- Benchmarks import the solver directly with synthetic instances — no DB, no fixtures, ms per run.
- Solver tests are pure, fast, deterministic unit tests.
- Algorithm swaps are a strategy-pattern config change, not a refactor.

Retrofitting this boundary later is miserable. It is the first thing built.

### 4.2 Job queue: Postgres `SKIP LOCKED`, not Redis + Celery

v1 uses a job queue implemented directly on Postgres:

```sql
UPDATE optimization_jobs SET status='running', started_at=now(),
       worker_id=$1, attempt=attempt+1, lease_expires_at=now()+interval '5 minutes'
WHERE id = (
  SELECT id FROM optimization_jobs
  WHERE status='queued' OR (status='running' AND lease_expires_at < now())
  ORDER BY queued_at
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
RETURNING *;
```

Rationale:
- **Cost.** Redis on a free tier cannot sustain Celery's constant broker polling; a paid Redis
  breaks the budget. This adds zero infrastructure.
- **Correctness is easier.** Job state and domain data commit in the *same transaction*. With an
  external broker you have a dual-write problem between broker and database.
- **The failure semantics are explicit.** Lease-based visibility timeouts, at-least-once delivery,
  idempotent effects, and crash recovery live in this codebase, where they can be read and tested
  directly, rather than in a framework's configuration.
- Migration to Redis/Celery later is a swap behind the `JobQueue` interface, if load ever warrants it.

Redis is added only when there is a measured reason: cross-instance SSE pub/sub, or a travel cache
hot enough that the Postgres L2 is the bottleneck.

**Why a separate worker at all, when greedy solves 40 people in ~10 ms.** Not for solver runtime
(§2 "Honest framing"). Running the solve inside the request fails in specific ways:

- **It stalls the API.** A CPU-bound solve in an `async` FastAPI endpoint blocks the event loop, so
  every other user's request waits. Threads only soften this under the GIL.
- **Restarts lose work silently.** A deploy or crash mid-solve drops it; a leased job is reclaimed.
- **External calls fail.** An ORS timeout or quota hit becomes a user-facing error instead of a
  backed-off retry.
- **Phones drop connections.** With a job id, the client reconnects and asks; without one, it
  re-submits and double-spends quota.
- **Unbounded concurrency.** Inline, every simultaneous request is a simultaneous solve. On a 2 GB
  host that also runs Postgres, a burst can reach the OOM killer, which may take Postgres with it.
  N workers cap concurrent solves at N; a burst queues and gets slower instead of falling over.
- **LNS is time-budgeted by design** (§8.3) — "search for 10 seconds" does not belong inside an
  HTTP request.

Throughput scales by adding worker processes against the same table — `SKIP LOCKED` is what lets
them share it without a coordinator. On a 2 vCPU host that is two workers at most; parallel solves
need processes, not threads.

**This is a decision point, not a foregone conclusion.** Week 2 executes inline behind the async
contract (§6), so the frontend never changes. In Week 4, build the separate worker if any of these
hold: LNS runs with a multi-second budget, solves have been lost to deploys, or ORS failures have
reached users. If none do, an in-process background task using the same claim/lease code is a
defensible v1, and splitting it out later remains a deploy change.

### 4.3 Realtime

Polling via TanStack Query in v1. Jobs complete in seconds; polling at 1s for the ~10s a job runs is
negligible load and removes an entire class of connection-state bugs.

SSE (not WebSockets) when it is worth it: the channel is unidirectional server→client, so SSE gives
auto-reconnect over plain HTTP with no connection lifecycle to manage. WebSockets would be strictly
more machinery for no additional capability.

### 4.4 Routing providers

One interface, three implementations:

| Impl | Used for | Cost |
|---|---|---|
| **OSRM** in Docker with a regional OSM extract | Local dev + the n=1000 benchmark suite | $0 (runs on the dev machine) |
| **OpenRouteService** (HeiGIT) matrix API | Production (n ≤ 50 per event, §2.4) | $0 on the free Standard plan |
| **Haversine × road-factor** | Fallback, and unit tests | $0 |

No free hosted API will return a 10⁶-entry matrix, which is exactly why the benchmark suite needs
local OSRM. Production events are small enough for a free tier.

**OpenRouteService, verified 2026-09-10.** `POST /v2/matrix/driving-car` with every point listed
once (participants + destination) and no `sources`/`destinations` returns the full directed square
matrix — one call covers both legs, since the return reads the destination's row. Base URL is
`api.heigit.org`; `api.openrouteservice.org` is deprecated. Keep it in config, not code.

| Limit (free Standard plan) | Value | Consequence |
|---|---|---|
| Matrix size per request | 3,500 sources × destinations | 51 × 51 = 2,601 fits: **no tiling** (§2.4) |
| Matrix size with "dynamic arguments" | 25 | Does not apply — requests send only `locations` and `metrics`. `distance` is not dynamic. |
| Matrix quota | 500/day · 40/min | One request per solve; fingerprint dedup and `travel_cache` make re-solves free |
| Directions quota | 2,000/day · 40/min | Binds before matrix — see below |
| Geocoding quota | 3,000/day · 100/min | Binds first for a public site — see below |

A 51-point test request (random points around a US college town) returned both metrics at
51 × 51 with no `null` cells and every point snapped within 82 m of a road. Adapter notes from it:
coordinates are `[lng, lat]` — a swap raises no error, only wrong answers, so pin it with a test;
durations arrive as floats and are rounded to integer seconds; a `null` cell means an unroutable
point and becomes an `unassigned` reason, not a crash; each point's `snapped_distance` is kept,
because a snap of hundreds of metres is a free signal that an address geocoded wrong (§7.2).

**Route geometry is fetched lazily.** Drawing a route takes one Directions call per car per leg —
~30 for a 50-person event, most of the per-minute quota and ~66 solves/day. So geometry is fetched
when someone first opens a route and then persisted (§7.5); a rider opening their own car costs
two calls. Straight segments between stops are an acceptable v1 rendering.

**Geocoding runs through the API, not from the browser.** Address autocomplete is a frontend
interaction, but the provider key must never ship to the browser — anyone could lift it and spend
the shared quota. Autocomplete fires per keystroke, so debounce it and require a few characters
before querying; a pasted roster geocodes each address once without autocomplete; `geocode_cache`
(§5.2) absorbs repeats. The geocoder remains a reversible choice (§11 item 4).

**Endpoints deliberately not used:** `/optimization` (a hosted routing-problem solver — it would
replace this project's solver) and everything else on the key besides matrix, directions, and
geocoding. The map must carry the attribution ORS returns: "openrouteservice.org | OpenStreetMap
contributors".

---

## 5. Data model

PostgreSQL 16 + PostGIS. `geography(Point,4326)` rather than float pairs: correct spherical
distance and GiST indexes for free. PostGIS availability is not a risk: development and production
run the same image, `postgres:16` with PostGIS installed (§10.1), so the extension is guaranteed in
both.

```sql
-- ── Events ──────────────────────────────────────────────────────────
events (
  id                   uuid primary key,
  public_id            text unique not null,          -- short slug for share URLs
  organizer_user_id    uuid null references users(id),-- null until accounts exist
  organizer_email      citext,
  name                 text not null,
  destination_address  text not null,
  destination_geog     geography(Point,4326) not null,
  arrival_at           timestamptz not null,
  ends_at              timestamptz not null,          -- return leg departs; drop-off ETAs count forward from it
  timezone             text not null,                 -- IANA
  status               event_status not null,         -- draft|open|locked|archived
  settings             jsonb not null default '{}',   -- objective weights, detour caps
  template_event_id    uuid null references events(id),-- roster reuse / clone lineage
  participants_version bigint not null default 0,     -- optimistic concurrency guard
  created_at           timestamptz not null default now(),
  check (ends_at > arrival_at)
);

-- ── Access tokens ───────────────────────────────────────────────────
event_tokens (
  id         uuid primary key,
  event_id   uuid not null references events(id) on delete cascade,
  kind       token_kind not null,          -- organizer|join
  token_hash bytea not null unique,        -- sha256; plaintext is never stored
  expires_at timestamptz,
  revoked_at timestamptz
);

-- ── Participants ────────────────────────────────────────────────────
participants (
  id                 uuid primary key,
  event_id           uuid not null references events(id) on delete cascade,
  display_name       text not null,
  email              citext,
  phone              text,
  role               participant_role not null,   -- driver|passenger|either
  seats_available    int not null default 0 check (seats_available >= 0),
  priority           int not null default 0,      -- generic; scales the unassigned penalty (§2.2)
  pinned_driver_id   uuid null references participants(id),  -- organizer override
  needs_outbound     boolean not null default true,
  needs_return       boolean not null default true,
  pickup_address     text not null,               -- ← the durable record (§5.2)
  pickup_geog        geography(Point,4326),        -- nullable; only persisted when user-supplied
  geocode_source     geocode_source not null default 'provider',  -- provider|user
  pickup_precision   precision_level not null default 'exact', -- exact|street|neighborhood
  earliest_departure timestamptz,
  latest_arrival     timestamptz,
  max_detour_minutes int,
  notes              text,
  status             participant_status not null default 'active',  -- active|cancelled
  token_hash         bytea not null unique,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
create index on participants using gist (pickup_geog);
create index on participants (event_id) where status = 'active';

-- ── Job queue ───────────────────────────────────────────────────────
optimization_jobs (
  id                uuid primary key,
  event_id          uuid not null references events(id) on delete cascade,
  status            job_status not null,     -- queued|running|succeeded|failed|cancelled
  algorithm         text not null,
  params            jsonb not null,
  input_fingerprint bytea not null,          -- dedup + idempotency
  input_version     bigint not null,         -- events.participants_version at enqueue
  idempotency_key   text,
  attempt           int not null default 0,
  max_attempts      int not null default 3,
  worker_id         text,
  lease_expires_at  timestamptz,             -- visibility timeout
  cancel_requested  boolean not null default false,
  progress          jsonb,
  error             text,
  queued_at         timestamptz not null default now(),
  started_at        timestamptz,
  finished_at       timestamptz
);
-- At most one in-flight job per event, enforced by the DATABASE, not app logic:
create unique index one_active_job_per_event
  on optimization_jobs (event_id) where status in ('queued','running');
create index jobs_claimable on optimization_jobs (queued_at)
  where status in ('queued','running');

-- ── Solutions ───────────────────────────────────────────────────────
solutions (
  id              uuid primary key,
  event_id        uuid not null references events(id) on delete cascade,
  job_id          uuid not null references optimization_jobs(id),
  algorithm       text not null,
  objective_value double precision not null,
  metrics         jsonb not null,   -- drive_s, vehicles, p95_detour_s, churn, gap_to_bound
  input_version   bigint not null,  -- stale if < events.participants_version
  is_active       boolean not null default false,
  created_at      timestamptz not null default now()
);
create unique index one_active_solution_per_event
  on solutions (event_id) where is_active;

-- One row per car. A car keeps the same riders both ways (§2.4), so a route covers both legs;
-- only the stop order and geometry are per leg.
routes (
  id                    uuid primary key,
  solution_id           uuid not null references solutions(id) on delete cascade,
  driver_participant_id uuid not null references participants(id),
  seats_used            int not null,
  total_distance_m      int not null,     -- both legs
  total_duration_s      int not null,     -- both legs
  detour_seconds        int not null,     -- both legs, vs the driver's direct round trip
  outbound_geometry     geometry(LineString,4326),  -- null until first viewed (§4.4)
  return_geometry       geometry(LineString,4326)   -- null until first viewed (§4.4)
);

route_stops (
  id             uuid primary key,
  route_id       uuid not null references routes(id) on delete cascade,
  leg            route_leg not null,  -- outbound|return; orders differ (§8.2)
  seq            int not null,
  participant_id uuid not null references participants(id),
  eta            timestamptz not null, -- pickup time outbound, drop-off time on return
  unique (route_id, leg, seq)
);

unassigned_participants (
  solution_id    uuid not null references solutions(id) on delete cascade,
  participant_id uuid not null references participants(id),
  reason         text not null,   -- no_capacity|detour_exceeded|time_window|no_drivers
  primary key (solution_id, participant_id)
);

-- ── Geocode cache — TTL'd, deliberately not a permanent store (§5.2) ─
geocode_cache (
  address_norm text primary key,   -- normalized address string
  lat          double precision not null,
  lng          double precision not null,
  provider     text not null,
  cached_at    timestamptz not null default now(),
  expires_at   timestamptz not null   -- evicted on expiry; never renewed in place
);

-- ── Travel matrix cache ─────────────────────────────────────────────
travel_cache (
  origin_cell bigint not null,     -- H3 (or geohash) cell id
  dest_cell   bigint not null,
  profile     text not null,       -- driving
  duration_s  int not null,
  distance_m  int not null,
  computed_at timestamptz not null default now(),
  primary key (origin_cell, dest_cell, profile)
);
```

### 5.1 Three decisions worth defending

**Duplicate-job prevention lives in the database.** `one_active_job_per_event` is a partial unique
index. Concurrent optimize requests from two API instances cannot both create a job: one insert
raises a unique violation, which the API catches and converts into `409 Conflict` returning the
existing job id. No distributed lock, no race window. `Idempotency-Key` on the request is a second,
independent layer (defense in depth against client retries and double-taps).

**Concurrent edits are handled optimistically, not by locking.** `events.participants_version` is a
monotonic counter bumped on every participant insert/update/delete. A job records the version it
read as `input_version`. On completion, if `events.participants_version != job.input_version`, the
solution is marked stale and — per event settings — automatically re-queued. The event is never
locked, participants are never blocked from editing, and the conflict is detected rather than
prevented. This is the answer to *"what happens if someone changes their pickup mid-solve."*

**The participant cap is race-free for the same reason.** Every insert already bumps
`participants_version`, which is an `UPDATE` on the event row and therefore takes that row's lock.
Counting active participants *after* the bump, in the same transaction, serializes concurrent
joins: two requests racing for the 50th seat cannot both see 49. The 51st gets `422`. No separate
lock, and no count check that a race can slip past.

**Idempotency comes from a content fingerprint.** `input_fingerprint` is a hash of the normalized
problem instance (sorted participant **address strings**, capacities, windows, destination,
algorithm, weights) — strings rather than coordinates, for the reason in §5.2.
A requested fingerprint that matches an existing succeeded solution returns that solution without
solving. This makes retries safe (an at-least-once queue with idempotent effects is effectively
exactly-once) and makes re-running an unchanged event instant.

The travel matrix is **never** stored on a job row — at n=1000 it is ~8 MB. It lives in
`travel_cache` keyed by cell pairs, so it is shared across every event in the same geography. For a
club that practices at the same venue weekly, that cache hit rate should be high, and it is a real
measurable number rather than a decorative one.

### 5.2 Addresses are the durable record; coordinates are derived

**The address string is what the system stores. Coordinates are resolved at solve time and cached
with a TTL.**

Most commercial geocoding terms restrict building a permanent database of provider-returned
coordinates — Google's have historically capped caching at ~30 days and additionally barred
displaying Google-derived geocodes on a non-Google map, which would conflict with MapLibre.
Persisting `pickup_geog` for every participant forever would sit squarely inside that restriction.

Storing the **user-entered address string** avoids the question entirely: it is the user's own
input, not provider output. `geocode_cache` then holds resolved coordinates with an explicit
`expires_at`, which is a performance cache rather than a derived database — and short-lived caching
is what these terms generally permit.

**The exception, and it matters:** a coordinate the *user* placed is not provider output. When the
coordinator drags a pin (§7.2), that lat/lng came from a human action in your UI. Those persist
permanently, flagged `geocode_source = 'user'`. So drag-to-correct still works, and corrections
survive re-geocoding rather than being overwritten by it.

Consequences worth accepting deliberately:

- **Geocoding moves inside the optimization job** — an O(n) fan-out against a rate-limited external
  dependency, resolved before the matrix build. This *strengthens* the case for the job being async
  (§2 "Honest framing") rather than weakening it.
- **`input_fingerprint` is computed over address strings, not coordinates** (§5.1). Geocoders drift;
  fingerprinting resolved coordinates would silently break idempotency when a provider nudges a
  result by ten metres. Fingerprint the input the user actually gave.
- **Recurring events carry addresses, not points.** Cloning last week's roster copies address
  strings, which re-resolve — so a provider improving its data improves next week's routes for free.
- Route geometry in `routes.geometry` is routing output, not geocoding output, and falls under the
  routing provider's terms. With OSM-derived routing (ORS, self-hosted OSRM) this is unencumbered.

**This also de-risks the plan.** Provider storage rights were the highest-blast-radius unknown in
§11; under this design no provider's storage terms can force a schema change, so the choice of
geocoder becomes reversible and can be made late. If per-solve geocoding ever becomes a bottleneck,
self-hosting Photon on the box already being paid for removes the constraint outright.

### 5.3 Why participant data is persisted, and how rosters are reused

Three distinct reasons, in order of necessity:

**1. The solve requires it.** Optimization runs in a *different process* from the one that received
the roster. The worker reads its input from the database — there is nowhere else for it to come
from. Even for a single one-off event that is never repeated, participant data must be persisted
between "the coordinator finishes typing" and "the worker runs." This reason alone is sufficient.

**2. Results and re-optimization reference it.** `route_stops` points at participants; the results
screen renders "pick up Jane at 1234 Regent St, 4:15pm" by joining through them. When a driver
cancels on Saturday morning, re-optimization needs the same roster still present.

**3. Reuse across recurring events.** The additive benefit — a weekly practice has the same roster
every week, and re-entering forty people is exactly the friction that sends a coordinator back to
their spreadsheet.

### 5.3.1 Snapshot vs. current state

Reuse raises a design question worth deciding deliberately, because both halves are needed:

- A **participation record** is an immutable snapshot: where Jane was *actually picked up* for the
  September 12 practice. Last week's solution must stay truthful even after Jane moves.
- A **person record** is current state: Jane's address *now*, used to prefill next week.

This is a slowly-changing-dimension problem. `participants` is the snapshot and always remains so.
The person record is the part that does not exist yet.

**v1 — clone-per-event.** `POST /events/{id}/clone` copies participant rows from the previous event
into a new one, carrying names, addresses, roles, and seat counts. No new tables, no ownership
model, and it removes ~95% of the re-entry work for a weekly practice. Corrections apply going
forward rather than retroactively, which is the correct behavior anyway.

**Later — a `people` address book.** A canonical roster owned by an organizer, with events
referencing people and snapshotting their details at solve time. This is strictly better, and it is
deferred for a concrete reason: an address book needs an *owner*, and ownership needs accounts,
which are outside the 6-week scope (`roadmap.md`). Clone-per-event does not block it — the
migration backfills `people` from existing participant rows and adds a nullable `person_id`.

### 5.3.2 Retention

An address book of home addresses that persists indefinitely is a materially larger privacy surface
than per-event snapshots, and the gap widens if the youth-sports use case ever arrives (§2). Decide
a retention policy before building the address book, not after: archive or purge participant
addresses some months after an event completes, keeping the aggregate metrics that make the
benchmarks and usage numbers meaningful. Cheap to add now, expensive to retrofit onto live data.

---

## 6. API

REST, versioned, JSON. Not GraphQL — a small fixed set of views with no client-shape variance.

```
── Events ──────────────────────────────────────────────────────────
POST   /v1/events                          → 201 {event, organizer_token, join_url}
GET    /v1/events/{public_id}              → payload shaped by caller's principal
PATCH  /v1/events/{public_id}              [organizer]
POST   /v1/events/{public_id}/lock         [organizer]  freeze submissions
POST   /v1/events/{public_id}/clone        [organizer]  new event, roster carried over

── Participants ────────────────────────────────────────────────────
POST   /v1/events/{public_id}/participants [join token] → 201 + participant_token
GET    /v1/participants/me                 [participant token]
PATCH  /v1/participants/me                 [participant token]   bumps participants_version
DELETE /v1/participants/me                 [participant token]   soft cancel
GET    /v1/events/{public_id}/participants [organizer]
PATCH  /v1/events/{id}/participants/{pid}  [organizer]  edit on someone's behalf

── Optimization ────────────────────────────────────────────────────
POST   /v1/events/{public_id}/optimizations [organizer]
         Idempotency-Key: <uuid>
         { algorithm?, weights?, preserve_previous?: bool }
       → 202 {job_id, status}
       → 409 {existing_job_id}   when one is already in flight
GET    /v1/optimizations/{job_id}          → {status, progress, solution_id?, error?}
DELETE /v1/optimizations/{job_id}          [organizer]  cooperative cancel

── Solutions ───────────────────────────────────────────────────────
GET    /v1/events/{public_id}/solutions              [organizer]  history
GET    /v1/events/{public_id}/solutions/{sid}        [organizer]
POST   /v1/events/{public_id}/solutions/{sid}/activate [organizer]
GET    /v1/events/{public_id}/assignment             [participant] redacted view
GET    /v1/events/{public_id}/solutions/{sid}/diff/{other} [organizer]

── Ops ─────────────────────────────────────────────────────────────
GET    /healthz  /readyz  /metrics
```

### 6.1 Authorization: three principals

No passwords, no OAuth. Three token types, all stored as SHA-256 hashes with expiries:

| Principal | Token | Grants |
|---|---|---|
| **Organizer** | `organizer_token` — shown once at creation, emailed | Full event control |
| **Participant** | `participant_token` — minted on join, set as httpOnly cookie *and* given as a resume link | Read/update own participant record; read own assignment |
| **Joiner** | `join_token` — embedded in the share URL | Create a participant on this event |

This is the right design for the product, not a shortcut. Accounts arrive later as an *upgrade*:
an authenticated user claims existing token-held participant records.

### 6.2 Field-level redaction

`GET /v1/events/{public_id}` returns different payloads per principal. Implement this with
**one explicit Pydantic response model per audience** — never by conditionally deleting keys from a
dict. Conditional deletion is how field leaks happen; separate serializers are auditable and
testable.

`GET .../assignment` is a participant's entire view: their driver's name and contact, their pickup
time, co-riders' first names, and the driver's full address **only once the solution is active**.
Full pickup addresses are visible only between a driver and their own assigned passengers.

This endpoint gets a dedicated test suite asserting that no unrelated participant's address, email,
or phone appears in the response under any solution state. Privacy here is a product requirement,
not a checkbox — the adjacent use case (youth sports) involves home addresses of minors behind a
forwardable link, and the design must be defensible before that use case arrives.

### 6.3 Cancellation is cooperative

`DELETE /v1/optimizations/{job_id}` sets `cancel_requested = true`. The worker checks the flag
between solver iterations and exits cleanly. Killing a worker mid-transaction is not safe and
pretending otherwise is a common mistake.

---

## 7. Client experience and the map

### 7.1 Principle: the list decides, the map verifies

Maps are the most common place a project like this wastes a week. The discipline that prevents it:

> **Decisions happen in the list. Verification happens in the map.**

Every mutating action — assign, pin, unassign, change seats, fix a bad address — lives in the roster
table or the results sidebar. The map exists to answer *"is this right?"*, not *"what should I do?"*
Direct manipulation on a map demos beautifully and is miserable on a phone, so it is deliberately
avoided except where dragging **is** the correction (§7.2, screen 2).

The interaction that ties them together is **linked highlighting**: hover or select in one view,
highlight in the other. That single pattern carries almost all of the map's value.

### 7.2 Screen by screen

**1 · Create event — confirm the destination.**
Address autocomplete drops a pin; the organizer can drag it. This matters more than it looks:
"Nielsen Tennis Stadium" geocodes to a building centroid, but the meeting point is a specific
parking lot entrance. Drag-to-adjust writes back a corrected `destination_geog`. Small feature, and
it silently improves every ETA the system will ever produce for that venue.

**2 · Roster entry — catch bad geocodes.**
The highest-value map in the application, and not the pretty one. All pickup points rendered at
once, so the coordinator can instantly spot the address that resolved to the wrong city. Geocoding
failures are silent and catastrophic: one bad coordinate distorts the entire solve.
- Click a dot → highlights its roster row (and vice versa).
- **Drag a dot → corrects that participant's coordinate.** The one place direct manipulation earns
  its keep, because the map *is* the error display.
- An "outlier" affordance: anything more than *n* km from the centroid gets flagged before solving.

**3 · Results — understand and sanity-check the assignment.**
- One color per driver; numbered stop markers showing pickup order.
- Hover a route → dim the others, highlight that car's roster in the sidebar.
- Click a person (list or map) → highlight their car and their stop number.
- **Outbound / return toggle**, since both legs are modelled (§8.2) and their orders can differ.
- Unassigned participants rendered in a visually distinct, hard-to-miss style. These are the most
  important markers on the screen and the easiest to accidentally under-emphasize.

**4 · Manual override.** Reassignment happens in the sidebar (select person → choose driver), which
sets `pinned_driver_id` and re-optimizes around it. Not by dragging markers between routes.

**5 · Participant view (Model B, later).** Mobile, and deliberately not an interactive map: a time,
a place, a driver name, in large type — plus a small static map for context. A participant needs to
know where to stand, not to explore a route.

### 7.3 Hand off navigation — do not build it

The single highest-ROI feature on the results screen is a **"Open in Google Maps" button per
driver**, with pickups pre-filled as waypoints:

```
https://www.google.com/maps/dir/?api=1
  &origin=<driver home>&destination=<venue>
  &waypoints=<stop1>|<stop2>|...&travelmode=driving
```

The return leg gets its own link with origin and destination swapped and the drop-offs in their
own order (§8.2) — not the outbound link reversed.

Roughly ten lines of code, and it is what a driver actually uses on Saturday morning. Turn-by-turn
navigation is a solved problem owned by companies with satellites; this project's job is to decide
*who picks up whom in what order* and then hand that off cleanly.

Convenient coincidence: the Maps URL API accepts up to 9 waypoints, and route length is already
capped at ≤ 8 stops by the Held–Karp bound (§8.2). The constraint never binds.

### 7.4 The dense-cluster problem — be honest about it

For club tennis the map will be visually mushy, and this should be expected rather than debugged:
40 pickup points inside a one-kilometre campus radius overlap heavily, and every route runs down the
same three streets. Zoomed to fit, it is a tangle.

Consequences:
- **For dense events the list is the primary interface and the map is the verification layer.** Do
  not spend week-3 hours polishing route rendering that a dense campus event cannot display legibly.
- Handle overlap explicitly: marker clustering at low zoom, and slight offsets for coincident routes
  so overlapping lines remain distinguishable.
- Route visualization becomes genuinely informative for the *general* product — weddings,
  conferences, spread-out suburbs — which is where demo screenshots should come from.

### 7.5 Technical notes

- **MapLibre GL JS.** Tiles from OpenFreeMap or self-hosted Protomaps (§11 item 5) — MapLibre is a
  renderer, not a tile source.
- **Route geometry is fetched once, then stored.** Fetched from the Directions API the first time a
  route is opened — not at solve time, because the Directions quota cannot absorb ~30 calls per
  solve (§4.4) — and persisted in `routes.outbound_geometry` / `return_geometry`, so every later
  view is a pure database read with no external calls.
- **Render as GeoJSON layers, not DOM markers.** Fine either way at n = 40; required for benchmark
  visualizations at n = 1000.
- **Do not encode meaning in color alone.** Beyond ~8 drivers, categorical palettes stop being
  distinguishable. Pair color with driver initials at the route midpoint and rely on
  hover-to-dim-others as the real disambiguator.
- **Degrade gracefully.** If tiles fail to load, the list view must remain fully functional. The map
  is never the only path to an answer.

### 7.6 Scope for the 6-week build

| Week 3 | Later |
|---|---|
| Destination pin with drag-to-adjust | Marker clustering / overlap offsets |
| All-pickups verification map + linked highlighting | Outlier detection before solve |
| Draggable pickup correction | Static participant map (Model B) |
| Colored routes with numbered stops | Animated route playback (probably never) |
| "Open in Google Maps" per driver, per leg | |
| Outbound / return toggle (the return leg is v1, §2.4) | |

---

## 8. Optimization

### 8.1 Objective

```
J =  w1 * Σ_routes  drive_time(r)
   + w2 * |vehicles|                                  ← parking-constrained venues weight this high
   + w3 * Σ_passengers  ride_time(p)                  ← passenger inconvenience
   + w4 * Σ_routes  max(0, time(r) - direct_time(driver_r))   ← driver detour
   + w5 * Σ_unassigned  (1 + priority(p))              ← large M, scaled by priority (§2.2)
   + w6 * churn(S, S_prev)                            ← re-optimization only
```

Both legs are counted: `drive_time(r)` and `ride_time(p)` sum over the outbound and return routes
(§8.2). A detour measured only on the outbound leg understates a driver's real burden by roughly 2x.

Subject to: seat capacity; per-driver `max_detour_minutes`; arrival by `arrival_at`; pickup no
earlier than `earliest_departure`; every active participant either assigned exactly once or listed
in `unassigned_participants` with a machine-readable reason.

Weights `w1…w6` live in `events.settings` so an organizer can bias toward "fewest cars" versus
"least inconvenience." This makes the objective a concrete, tunable product feature rather than a
hand-wave.

### 8.2 The structural insight

**A driver's home is the origin of their own route.** Drivers are `participants` rows like anyone
else — their `pickup_geog` is where they start. So the outbound route is
`driver_home → pickup₁ → … → pickupₖ → venue`, and a driver's detour is that path minus their
direct `home → venue` time. Assigning a driver passengers who live away from their own commute
corridor is therefore already expensive under the objective; nothing special is needed to express it.

**The return leg is sequenced independently, and the reason is asymmetry -- not fairness.**
After the event the route is `venue -> dropoff1 -> ... -> dropoffk -> driver_home`, over the same
node set with the driver's home as the *terminus*.

The intuitive guess is that reversing the outbound order is merely a good approximation. It is
better than that: under a **symmetric** travel matrix, reversal is exactly optimal, for drive time
and total ride time both. With outbound edges `e0..ek` the occupancy runs `0,1,...,k`, so the ride
sum is `1*e1 + 2*e2 + ... + k*ek`; reversed, occupancy runs `k,...,1,0` over the same edges in the
opposite order and sums to precisely the same value. No ride weight can separate them.

What does separate them is that **real routing matrices are not symmetric**. One-way streets, turn
restrictions, and divided highways all make `a -> b` differ from `b -> a`, and OSRM and ORS return
asymmetric tables accordingly. Sequencing the return independently costs nothing -- the same
Held-Karp routine with a different terminus -- and is the only way to exploit that.

**Measured, and the honest shape of it.** In the 51-point ORS test matrix (§4.4), 66% of point pairs
differ by at least a second between directions -- but the median difference is 4 s (0.9%). The
tail is what matters: 10% of pairs differ by 38 s (7.7%) or more, and the worst by five minutes
(489 s one way, 787 s back), with one location in all five of the most lopsided pairs -- a one-way
or divided road nearby. So independent return sequencing changes little on most routes and pays
off on the few that pass a spot like that. Describe it that way; do not claim an average saving.
These are random points on a real road network, not a real event.

**A fairness note, stated honestly.** Reversal does mean the passenger collected first is also
dropped last, riding longest in both directions. A *sum* of ride times is utilitarian by
construction and cannot see this: it prices total burden, never its distribution. Expressing
"nobody should ride far longer than anyone else" needs a different term -- a maximum ride time, or
a squared penalty on it. That is a legitimate future refinement of the objective, and it is
deliberately **not** claimed as current behaviour.

Because every route terminates at the same node, a driver's outbound route is a **shortest
Hamiltonian path** over their assigned pickups ending at the destination. For ≤ 8 stops — which covers every real
passenger car — **Held–Karp dynamic programming solves this exactly** in ~2⁸·8² operations, i.e.
microseconds.

Therefore: **route sequencing in this system is never approximate. Only the assignment is heuristic.**
Every solver below competes only on assignment; none of them can produce a badly ordered car.

### 8.3 Algorithm ladder

| # | Algorithm | Role | Scale | v1? |
|---|---|---|---|---|
| 1 | **Greedy insertion** — passengers sorted by distance from destination desc., each inserted at the cheapest feasible position | Baseline; always produces a feasible answer | any | ✅ |
| 2 | **CP-SAT (OR-Tools)** exact model | Ground truth; proves optimality for n ≲ 40 and yields the optimality gap. **Benchmarks only — never run on a user request** | small | ✅ |
| 3 | **LNS** — ruin-and-recreate with relocate / swap / 2-opt under simulated-annealing acceptance | The production algorithm; hand-written against this objective | 1000+ | ✅ |

**Production runs greedy, then LNS within a time budget. CP-SAT is a measuring instrument, not a
product feature.** A proven optimum and an LNS answer within a few percent differ by seconds of
driving in a dense campus cluster, which no user can perceive (§2: the value is coordination, not
mileage). Meanwhile CP-SAT costs ~400 MB per solve on a 2 GB host, has high runtime variance, and
the 50-participant cap (§2.4) sits past the ~40 where it reliably proves optimality. Keeping it out
of production also keeps OR-Tools out of the production image — it is a benchmark-only
dependency. *Trigger to revisit:* the benchmarks show LNS more than ~5% off optimal on 20–25
participant instances; then run CP-SAT with a time limit for small events and fall back to LNS.
The strategy interface makes that a configuration change.
| 4 | **Min-cost flow** relaxation | Lower bound + warm start | any | stretch |
| 5 | **OR-Tools Routing** (CVRP, single depot) | Mid-scale reference point | ≤ 300 | later |

**On min-cost flow — a correctness caveat.** Flow is exact only when the cost of assigning passenger
*p* to driver *d* is independent of who else rides with *d*. That is false here: the marginal cost of
a third passenger depends on the route already formed by the first two. Costs are supermodular, so
flow does not solve the real problem. Its honest role is as a **relaxation producing a lower bound**
and a **warm start** — the correct use of it, for the same amount of code.

#2 exists to make the quality of #1 and #3 measurable. *"LNS lands within X% of proven optimal on
instances CP-SAT can close, and scales to 1000 participants in Y seconds where CP-SAT times out"*
can only be measured if the exact solver is built.

### 8.4 Re-optimization and churn

The initial solve is the easy part. Every real event changes: drivers cancel, latecomers join. A
re-optimization that reshuffles everyone is useless — people have already made plans.

So `w6 * churn(S, S_prev)` penalizes changes relative to the previously *activated* solution
(count of passengers whose assigned driver changed, weighted). This is a minimum-perturbation /
warm-start problem, and it is what makes the product actually usable week to week.

### 8.5 Benchmarking

Synthetic instance generator, fixed seeds, three spatial distributions:

- **uniform** — worst case, no structure to exploit
- **clustered** — suburbs; realistic for the general product
- **radial** — commuter corridors; realistic for campus and school events

Grid: n ∈ {20, 50, 100, 250, 500, 1000} × driver ratio ∈ {0.2, 0.35, 0.5}.

Per cell record: objective, vehicles used, mean and p95 passenger detour, wall-clock runtime, and
gap to the CP-SAT bound where available. Commit results as JSON; render charts from that JSON.

**Run a small subset in CI as a regression gate** — if a refactor degrades solution quality by more
than a threshold, the build fails. Unit and property tests cannot catch this: a refactor can keep
every solution feasible while making all of them worse.

---

## 9. Engineering concerns, and where each is handled

Each concern maps to a concrete part of the system:

| Concept | Concrete artifact |
|---|---|
| Algorithms | Ladder of solvers with measured optimality gaps against a CP-SAT bound |
| Geospatial | PostGIS `geography` + GiST, `ST_DWithin` candidate pruning, self-hosted OSRM matrix service |
| Concurrency | Optimistic `participants_version` instead of locking; conflict detection + auto-requeue |
| Race conditions | Partial unique index enforcing one in-flight job per event; `Idempotency-Key` as a second layer |
| Idempotency | `input_fingerprint` — identical input returns the cached solution without re-solving |
| Async processing | `SKIP LOCKED` queue with lease-based visibility timeouts, bounded retries, cooperative cancellation, progress checkpointing |
| Worker failure | Expired-lease reclaim + idempotent effects ⇒ at-least-once delivery with exactly-once outcome |
| Caching | Travel cache keyed by H3 cell pairs, shared across events in a geography, with a measured hit rate |
| AuthZ | Three principals, per-audience response schemas, address redaction gated on solution state |
| Testing | Pure solver unit tests; testcontainers integration tests against real Postgres; Hypothesis property tests asserting feasibility invariants; benchmark regression gate |
| Observability | Structured JSON logs with job correlation ids; solve-time histograms by algorithm and n; Sentry; CloudWatch alarms on instance health |
| Infrastructure as code | Terraform: VPC, security group, EC2, IAM instance role, backup bucket, GitHub OIDC role (§10.1) |
| Credential hygiene | No long-lived AWS credentials anywhere: instance role for S3, SSM instead of SSH, OIDC for CI, SSO for the developer |
| CI/CD | lint → typecheck → unit → integration → benchmark gate → build arm64 image → deploy via OIDC |

Property-based testing is the cheapest high-value item on this list: generate random instances,
assert every returned solution satisfies capacity, time windows, detour caps, and exactly-once
assignment. Hypothesis will find solver bugs faster than manual testing will.

---

## 10. Tech stack

| Layer | Choice | Reason |
|---|---|---|
| DB | Postgres 16 + PostGIS, self-hosted in Docker on the instance | Correct spherical distance, GiST indexes, `SKIP LOCKED`. Same multi-arch image in development and production; no free-tier compute limits (§10.1). |
| ORM | SQLAlchemy 2.0 async + Alembic | Migrations from commit one. |
| API | FastAPI + Pydantic v2 | OpenAPI → generated TypeScript client. |
| Queue | Postgres `SKIP LOCKED` (see §4.2) | Zero added infra; transactional with domain writes. |
| Routing | OSRM local (bench) / ORS (prod) / haversine (fallback), one interface | $0. One matrix request per event (§4.4). |
| Geocoding | Address autocomplete in the UI, proxied through the API | The provider key never reaches the browser (§4.4). |
| Solver | Hand-written greedy & LNS in production; OR-Tools CP-SAT in benchmarks only | Owned heuristic + exact bound to measure it against (§8.3). |
| Realtime | Polling (TanStack Query); SSE later | Unidirectional channel; no connection state. |
| Maps | MapLibre GL + OSM tiles | Free and OSS; consistent with OSRM. |
| Frontend | Next.js App Router, TypeScript, Tailwind, TanStack Query (Vercel free tier) | Mobile-first. |
| Testing | pytest + testcontainers + Hypothesis | Never SQLite — the schema uses PostGIS and partial indexes. |
| Lint/types | Ruff + mypy (strict on `domain/`) | Strict where it matters. |
| Observability | structlog JSON + Sentry free tier (+ OpenTelemetry later) | $0. |
| CI | GitHub Actions, deploying to AWS via OIDC | No AWS credentials stored in the repo. |
| Infrastructure | Terraform (state in S3), IAM, SSM Session Manager, CloudWatch | Reproducible, reviewable infrastructure; see §10.1. |
| Hosting | Vercel (web, free) + **one always-on EC2 `t4g.small`** running Caddy, api, worker, and Postgres | ~$17.50/month, covered by AWS credits for ~11 months. See §10.1. |

### 10.1 Deployment topology

A single always-on EC2 instance, Docker Compose, Caddy in front for automatic TLS, all provisioned
by Terraform:

```
Vercel (free) ──────► Caddy :443  ── auto TLS     EC2 t4g.small (Graviton, arm64)
                        │                         us-east-1, public subnet of its own VPC
                        ├─► api      (uvicorn, FastAPI)
                        └─► worker   (same image, different entrypoint)
                                │
                        postgres     (postgres:16 + PostGIS, no published port)
                                │
                                └─► nightly pg_dump ──► S3 (via instance role)

Operator ── SSM Session Manager (no SSH port)     GitHub Actions ── OIDC role ──► deploy
```

**API and worker are separate processes, co-located on one machine.** This is the important
distinction: the architecture is genuinely two-tier — independent process lifecycles, crash
isolation, a real queue between them — and moving the worker to its own machine later is a deploy
config change, not a refactor. Co-locate the processes; do not co-mingle the code.

**Why an always-on box rather than scale-to-zero:** it resolves §11 item 2 (the `SKIP LOCKED`
worker must be running to poll), and it removes cold-start latency for the first visitor after an
idle stretch — which, for a weekly event, is most visitors. At this scale the box is idle almost
always, which is fine.

**Why EC2 rather than Lightsail** (decided 2026-09-10, superseding Lightsail the same day).
Lightsail is the simpler product — flat $12 with IPv4, disk, and transfer bundled. The deciding
difference is credentials. A Lightsail instance cannot assume an IAM role, so anything the box does
against AWS — the nightly S3 backup, for one — needs a long-lived access key stored on the machine,
and shell access means an open SSH port with keys to manage. For a public repository whose hard
rules are about keeping secrets out of reach, that is the wrong default. EC2 removes both, at
~$5.50/month more, and brings network and access controls under the same infrastructure code:

- **Terraform** for everything below — the infrastructure is reviewable in a pull request and
  rebuildable from nothing. `terraform plan` also makes every billable resource visible before it
  exists, which is the best defence against AWS's bill traps.
- **A small VPC of its own** — one public subnet, internet gateway, route table. No NAT gateway.
- **A security group allowing only 80 and 443.** No port 22 at all.
- **SSM Session Manager** for shell access, authenticated by IAM, instead of SSH keys and an open
  port.
- **An IAM instance role** that lets the box write backups to S3 — no credentials on the machine.
- **GitHub Actions deploys through an OIDC-federated role** — no AWS keys stored in the repo, which
  matters doubly because the repo is public.
- **CloudWatch alarms** on status checks, CPU credits, and disk.

The result is that **no long-lived AWS credential exists anywhere**: the instance has a role, CI
has OIDC, and the developer uses short-lived IAM Identity Center (SSO) sessions for Terraform.

**Why `t4g.small`.** 2 vCPU and 2 GB, the same shape as the Lightsail plan. Graviton (arm64) is
~$3/month cheaper than the x86 `t3.small`, and it matches the development machine (Apple Silicon),
so images run natively in both places. Burstable CPU is right for a box that is idle almost always
and solves in bursts of seconds.

**Cost, us-east-1 on-demand:** instance ~$12.26, 20 GB gp3 disk ~$1.60, public IPv4 ~$3.65,
transfer $0 under the 100 GB/month free allowance, S3 backups cents — **~$17.50/month**, against
$12 for Lightsail. New AWS accounts receive up to $200 in credits valid 12 months, which covers
~11 months of it. After that, a 1-year Compute Savings Plan cuts the instance line by roughly 30%.
IPv4 is not optional: IPv6-only would strand users on IPv4-only networks, and making outbound calls
to IPv4-only services from an IPv6-only subnet needs a NAT gateway (~$32/month).

Hetzner was cheaper on paper, but its cost-optimized line was sold out and its next tier started at
$14.09, with the same stored-credential problem for off-box backups.

**The PostGIS image must be multi-arch.** `postgis/postgis` publishes amd64 only (checked on Docker
Hub, 2026-09-10) — it already runs under emulation on the Apple Silicon dev machine and would do
so on Graviton. Build a small image instead, `FROM postgres:16` plus Debian's
`postgresql-16-postgis-3` package; both are published for arm64 and amd64. One image, native
everywhere.

**Terraform state never enters the repository.** State files can hold secrets in plain text and
this repository is public. State lives in an S3 backend; `*.tfstate*` and `.terraform/` are
gitignored before the first `terraform init`.

**Why Postgres on the box rather than managed** (reverses the earlier choice of Neon, 2026-09-10):
Neon's free plan allows 100 CU-hours per month; a worker polling every second never lets the
database suspend, which at the smallest compute size is ~183 CU-hours (730 h × 0.25 CU). Fitting
the allowance would mean engineering around the free tier — wake-on-enqueue, cold starts on the
first request. Self-hosting instead gives guaranteed PostGIS, sub-millisecond queries, no pooler
constraints, and parity with the development image. The cost is ~250 MB of RAM and owning backups.

**The database port is never published.** The development `docker-compose.yml` maps `5432:5432`,
which binds every interface — and Docker's port publishing bypasses the host firewall. The
production compose file publishes no database port; api and worker reach Postgres over the
compose network. The security group allows only 80 and 443 regardless.

**Sizing (estimates, to be measured):** ~250 MB API, ~150–250 MB worker (greedy + LNS; CP-SAT is
not deployed, §8.3), ~250 MB Postgres, ~300 MB Caddy + OS — roughly 1–1.1 GB of the instance's 2 GB, plus
a swap file as a safety margin. OSRM stays on the dev machine (§4.4) and is never deployed.

**AWS bill traps.** A single instance in a *public* subnet with a security group, and Caddy
terminating TLS. No Application Load Balancer (~$16/mo), no NAT Gateway (~$32/mo) — both cost more
than the compute they would front here. Other quiet charges: an Elastic IP left unattached, EBS
snapshots, oversized volumes, CloudWatch Logs ingestion. Terraform declares every resource, so
nothing exists that `plan` does not show and `destroy` cannot remove. A zero-spend budget and a
monthly cost budget with forecast alerts are set before launching anything. The application itself
uses nothing AWS-specific beyond S3 for backups, so it stays portable to any Docker host — including
a home server behind Cloudflare Tunnel.

**Backups are load-bearing.** With Postgres self-hosted, the nightly `pg_dump` is the *only* copy.
It goes to an S3 bucket written through the instance role — no backup credentials exist — with
versioning on and a lifecycle rule expiring old dumps. The trade-off, accepted: backups share the
AWS account with the thing they back up. At this scale, versioning covers accidental deletion; an
off-AWS copy would reintroduce a stored credential. The job runs from the first real event, and at
least one restore is rehearsed before the project is presented.

### Deferred infrastructure, and its trigger

| Deferred | Add when |
|---|---|
| Redis | SSE needs cross-instance pub/sub, **or** `travel_cache` reads become a measured bottleneck |
| Celery | Job volume outgrows a single worker's `SKIP LOCKED` polling loop |
| SSE | Polling load becomes visible, or solves routinely exceed ~30s |
| Accounts | Organizers ask for event history across devices |
| AWS ECS | The single instance becomes the constraint — deploy downtime matters, or api and worker need to scale independently. The Terraform already exists; this is a module, not a migration. |
| A dedicated worker machine | One worker's solve queue backs up, or a runaway solve starves the API |
| Managed Postgres (RDS, Neon paid) | Operating the database becomes a measurable cost, or the data must outlive the instance |
| CP-SAT in production | Benchmarks show LNS > ~5% off optimal on small events (§8.3) |
| Flexible drivers (`Role.EITHER`, §2.3) | The coordinator wants the system to choose how many cars go, not just who rides in them |

Starting on one Terraform-managed instance rather than ECS keeps the first deploy small; ECS stays
deferred until a single box is measurably the problem.

---

## 11. Free-tier research checklist

Limits and terms change often, so these are questions to answer rather than facts to trust. Ordered
by blast radius: the first four can force a design change, the rest only affect cost or polish.

**Status as of 2026-09-10 — all Tier 1 design blockers are resolved:**

| Item | Resolution |
|---|---|
| 1. Matrix limits | **Resolved.** ORS allows 3,500 sources × destinations per request; the 50-participant cap keeps every event to one call. Verified with a live 51-point request (§4.4). |
| 2. Always-on process | **Resolved.** An EC2 instance runs whatever is started on it (§10.1). |
| 3. PostGIS on managed Postgres | **Moot.** Postgres is self-hosted with PostGIS installed in the image; Neon's free compute allowance could not sustain a polling worker (§10.1). |
| 4. Geocoding provider | Open, still reversible. ORS geocoding (3,000/day) is the default candidate. |
| 6. Backend host | **Resolved.** AWS EC2 `t4g.small`, `us-east-1`, provisioned with Terraform (§10.1). Lightsail was chosen first and superseded the same day. |
| 7. Managed Postgres | **Moot** (see 3). |
| 5, 8–12 | Open; none blocks Week 2. |

### Tier 1 — could force a design change

**1. Matrix / distance API: max coordinates per request.**
Determines whether tiling logic is needed. A cap of 25 coordinates means a 40-person event needs 4
sub-matrix calls and a 60-person event needs 9 — plus stitching and partial-failure handling.
Find: max coordinates per matrix request · requests per day and per minute · whether results may be
cached. *If tiling is required:* it belongs in the matrix builder behind the routing interface, and
it is a legitimate reason for the job to be async.

**2. Does the chosen host support an always-on background process?**
A `SKIP LOCKED` worker polls the database, so it must be running — which is in direct tension with
the scale-to-zero behavior that makes free tiers free (Cloud Run, Render free, Fly auto-stop). Three
resolutions, in order of preference for v1:
  a. **Run the worker as an in-process background task inside the API.** Keeps the claim/lease logic
     intact and splittable later, costs nothing, and is honest at this scale.
  b. One small always-on machine for the worker.
  c. Trigger the worker by HTTP/Cloud Tasks instead of polling.
Postgres `LISTEN/NOTIFY` reduces latency but still needs a live connection, so it does not solve this.

**3. PostGIS on the managed Postgres free tier.**
Confirm the extension can be enabled. Also check: auto-suspend behavior and cold-start latency
(a scale-to-zero database behind a scale-to-zero API compounds into a slow first page load),
storage cap, and connection limits — asyncpg pooling against a low connection cap needs the
provider's pooler endpoint. *Fallback:* lat/lng columns plus a haversine helper (§5).

**4. Geocoding provider — now a *reversible* choice, not a blocking one.**
Under §5.2 no provider's storage terms can force a schema change, so pick on ergonomics and free-tier
request volume rather than on licensing. Still worth a skim of the terms for two things: whether
short-lived caching is permitted at all, and whether results may be displayed on a non-Google map
(Google's terms have historically said no, which would rule it out alongside MapLibre).
*Candidates:* Mapbox Search · Photon (OSM, self-hostable on the box you already run) · Nominatim
(OSM, usage-policy limited).

### Tier 2 — cost and user experience

**5. Map tiles.** MapLibre is a renderer, not a tile source — this is easy to miss until the map
renders blank. Find the monthly map-load or tile-request cap for: OpenFreeMap (no API key) ·
Protomaps (self-host a `.pmtiles` file on object storage — effectively free and fully under your
control) · MapTiler · Stadia Maps.

**6. Backend host, current pricing.** Free allowances have been withdrawn across this category
recently, so verify rather than assume. Compare on: scale-to-zero behavior, cold-start latency,
whether a second always-on process is affordable (see #3), and monthly floor.
*Candidates:* Fly.io · Render · Railway · Google Cloud Run · Koyeb.

**7. Managed Postgres comparison.** Storage, compute hours, and specifically **inactivity
behavior** — a tier that *pauses* a project after a week of no traffic is bad for a public site
whose traffic is sporadic.

### Tier 3 — confirm and move on

**8. Vercel Hobby** — the non-commercial-use restriction is real; fine for a free site, not
if it is ever monetized. Cloudflare Pages is the alternative without that clause.
**9. Sentry** — error events per month on the developer tier.
**10. Resend** (or alternative) — emails/day and /month, and whether a verified sending domain is
required (it usually is; budget an hour of DNS).
**11. GitHub Actions** — minutes are unlimited on **public** repositories. Making the repo public is
free CI; decide early, because scrubbing history later is unpleasant.
**12. Geofabrik OSM extract** — download size for the target region and the RAM `osrm-routed` needs
after preprocessing (CH and MLD have different memory profiles). Local-only, so this is a laptop
constraint, not a hosting cost.

### Answered 2026-09-10

- *Does club tennis want return-leg coordination in v1?* Yes — with the same riders both ways (§2.4).
- *Default `pickup_precision` for a campus roster?* Exact address (§2.4).
