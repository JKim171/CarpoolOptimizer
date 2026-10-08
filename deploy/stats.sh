#!/bin/bash
# Usage numbers, read out of the production database. Run by hand over SSM:
#
#   aws ssm start-session --target <instance> --profile <profile>
#   sudo /opt/carpool/stats.sh
#
# It ships in the image's deploy/ directory and the deploy copies that into the
# project directory, so the script on the box is always from the same build as
# the schema it reads. Nothing has to be installed for it, and unlike the backup
# it is on no timer: it answers a question when someone asks it.
#
# This exists instead of putting product analytics in the frontend. The questions
# worth asking -- did anyone create an event, did they get as far as an answer,
# how big are the rosters -- are facts about rows in this database, and no
# JavaScript tag can answer them accurately: it sees the browsers that loaded and
# ran it, which is neither all of them nor only real ones. The page-view side
# lives in Vercel Web Analytics and deliberately excludes event pages
# (apps/web/lib/analytics.ts). This is the other half.
#
# NOTHING HERE PRINTS PARTICIPANT DATA. Every query below is an aggregate -- a
# count, a percentile, a bucket. This database holds children's home addresses
# (CLAUDE.md, docs/design.md 5.3.2), so a stats script is exactly the kind of
# thing that grows a `select name, address` while someone is debugging and then
# gets pasted into an issue. It reads in a read-only transaction so it cannot
# write, and the output is reviewed on that basis: if a column here would name a
# person or a place, it does not belong in this file.
set -euo pipefail

: "${APP_DIR:=/opt/carpool}"

cd "$APP_DIR"

# -A: no table alignment, which keeps the output diffable between runs.
# -X: ignore any ~/.psqlrc, so output does not depend on the invoking user.
# default_transaction_read_only: the guarantee is set by the server for this
# session rather than promised by the SQL below. A stray write in an edit to this
# file fails rather than running.
#
# Same connection story as backup.sh: psql runs inside the Postgres container
# over its unix socket, which the official image trusts, so no credential is
# read, passed, or exported here.
docker compose exec -T postgres \
  psql -X -U carpool -d carpool -v ON_ERROR_STOP=1 \
  -c 'set default_transaction_read_only = on' \
  -f /dev/stdin <<'SQL'
\timing off
\pset pager off

\echo
\echo === as of ===
select now() at time zone 'utc' as utc_now;

\echo
\echo === events ===
-- The closest thing to "how many users" that this schema can answer. There are
-- no accounts yet (events.organizer_user_id is null until they exist, design 6.1),
-- so one organizer running three events is three rows here and cannot be told
-- apart from three organizers. Read this as events, not people, and do not
-- quietly start calling it users.
select
  count(*)                                                    as events_total,
  count(*) filter (where created_at >= now() - interval '7 days')  as last_7d,
  count(*) filter (where created_at >= now() - interval '30 days') as last_30d,
  count(distinct organizer_email)                             as named_organizers
from events;

\echo
\echo === events by status ===
select status, count(*) as events
from events
group by status
order by events desc;

\echo
\echo === the funnel that matters ===
-- An event with no solution is someone who typed a roster and left, or never got
-- as far as a roster. That gap is the product problem; the absolute count is
-- vanity next to it.
select
  count(*)                                        as events,
  count(*) filter (where p.active > 0)            as with_a_roster,
  count(*) filter (where s.solutions > 0)         as reached_an_answer
from events e
left join lateral (
  select count(*) as active
  from participants
  where event_id = e.id and status = 'active'
) p on true
left join lateral (
  select count(*) as solutions
  from solutions
  where event_id = e.id
) s on true;

\echo
\echo === roster sizes, for events that have one ===
-- Percentiles rather than a list of events and their sizes: the shape of demand
-- is the useful fact, and it says nothing about any particular group. The 50-cap
-- is the number to watch against max.
select
  count(*)                                                       as events_with_a_roster,
  min(active)                                                    as smallest,
  round(percentile_cont(0.5) within group (order by active))      as median,
  round(percentile_cont(0.95) within group (order by active))     as p95,
  max(active)                                                    as largest
from (
  select event_id, count(*) as active
  from participants
  where status = 'active'
  group by event_id
) r;

\echo
\echo === optimization jobs by status ===
-- failed and cancelled are the interesting rows. A rising failed count is a bug
-- report nobody filed.
select status, count(*) as jobs
from optimization_jobs
group by status
order by jobs desc;

\echo
\echo === solves per event, for events that solved at least once ===
-- Re-optimizing is the organizer arguing with the answer, which is a signal
-- about the objective weights rather than about usage.
select
  count(*)                                                        as events_that_solved,
  round(avg(solves), 2)                                           as mean_solves,
  max(solves)                                                     as most_solves
from (
  select event_id, count(*) as solves
  from solutions
  group by event_id
) s;
SQL
