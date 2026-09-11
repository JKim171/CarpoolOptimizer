# Architecture diagrams

How CarpoolOptimizer is deployed, and what one optimization request does end to end. This is the
planned architecture as of 2026-09-10: today only the solver (`packages/domain`) and CI are built.
The reasoning behind each piece is in [`../design.md`](../design.md) §4, §4.2, §4.4, and §10.1.

## What runs where

![Deployment topology: phones reach the web app on Vercel and send API calls over HTTPS to Caddy on a single EC2 instance, the only inbound path. Caddy proxies to the api; the api and worker share a Postgres container whose port is never published. The worker calls OpenRouteService once per solve. GitHub Actions deploys through an OIDC role, SSM provides shell access and runs deploys, Postgres dumps nightly to a versioned S3 bucket through the instance role, and CloudWatch alarms watch the instance. The developer laptop provisions everything with Terraform and runs benchmarks locally.](deployment.svg)

Everything server-side runs as containers on one EC2 instance. The only path in from the internet is
HTTPS to Caddy (amber); shell access and deploys arrive through SSM and IAM, never through an open
port. CI pushes images to GitHub's container registry and deploys by SSM Run Command, restricted to
a single deploy document (design §10.1).

- Three nested boundaries — VPC, security group, instance — and only ports 80 and 443 cross them
  inbound. Postgres's port never leaves the Docker network.
- The worker has no inbound port at all. It pulls work from Postgres, so adding a second worker is
  just starting another process.
- Outbound calls leave through the internet gateway. There is no NAT gateway, which would cost more
  (~$32/month) than the instance itself.
- The developer laptop provisions everything with Terraform and keeps the benchmark tools. OSRM and
  CP-SAT never ship to the server.

## One optimization, end to end

![Sequence of one optimization: the phone posts to the api, which inserts a queued job in Postgres and immediately returns a job id. The worker claims the job with SKIP LOCKED and a five-minute lease, fetches drive times from OpenRouteService in one matrix call, runs greedy then LNS then validation, and writes the solution and marks the job succeeded in one transaction. Meanwhile the phone polls the job every second until it succeeds. Until week 4 the api runs steps four through seven itself.](optimization-sequence.svg)

The phone gets a job id immediately and polls; the worker does the slow part. A crash mid-solve
leaves the lease to expire and another claim to pick the job up. Until week 4 the api runs steps 4–7
itself behind the same contract, so the web app never changes.

## Who holds which credential

Only the last two rows are long-lived secrets, and neither touches AWS.

| Who | Proves identity with | Lives for |
|---|---|---|
| A developer, running Terraform or a shell | IAM Identity Center (SSO) | hours |
| GitHub Actions deploy | OIDC token → deploy role (can send only the deploy document) | one workflow run |
| The EC2 instance | IAM instance role | rotated by AWS |
| App → OpenRouteService | `ORS_API_KEY` in `.env` on the instance | until rotated |
| api, worker → Postgres | DB password in `.env`; never leaves the compose network | until rotated |

## Monthly cost

us-east-1, on-demand.

| Line item | USD |
|---|---:|
| EC2 `t4g.small`, 730 hours | 12.26 |
| EBS gp3, 20 GB | 1.60 |
| Public IPv4 address | 3.65 |
| Data out, under the 100 GB free allowance | 0.00 |
| S3: Terraform state and backups | ~0.05 |
| Vercel, OpenRouteService, Sentry free tiers | 0.00 |
| **Total** | **~17.50** |

The diagrams are hand-written SVG. Edit them directly; they carry their own light and dark palettes.
