#!/bin/bash
# The nightly pg_dump, run on the instance by carpool-backup.timer.
#
# Postgres is self-hosted on this box's own EBS volume, so what this script
# uploads is the ONLY copy of the database that is not on the machine
# (docs/design.md 10.1). That is the whole reason it exists, and it is why every
# failure path below exits non-zero rather than carrying on: a backup that
# quietly produced nothing is worse than no backup, because it looks like one.
#
# It ships in the image's deploy/ directory, so the script that runs is always
# from the same build as the code and the schema it dumps -- the same property
# the compose file and Caddyfile have.
set -euo pipefail

# Participant home addresses pass through the staged file below (CLAUDE.md,
# "never commit real participant data" -- the same data, one layer out). 077
# here means every file this script creates is private to root from the moment
# it exists, rather than being chmod-ed a line later.
umask 077

: "${APP_DIR:=/opt/carpool}"
: "${BACKUP_BUCKET:?BACKUP_BUCKET must name the destination bucket}"
: "${BACKUP_PREFIX:=dumps}"
: "${AWS_REGION:=us-east-1}"
: "${BACKUP_LOCK:=/run/carpool-backup.lock}"

log() { printf '%s backup: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "FAILED: $*"; exit 1; }

cd "$APP_DIR"

# One dump at a time. The timer could fire again while a slow dump is still
# running (a throttled box on an exhausted CPU credit balance), and two
# concurrent pg_dumps would compete for the same connection budget for no gain.
# -n: fail immediately rather than queueing a second run behind the first.
exec 9>"$BACKUP_LOCK"
flock -n 9 || fail "another backup is already running"

# Timestamped to the second, in UTC, and never reused. A same-night re-run
# therefore writes a NEW key instead of replacing an existing one, which is
# what keeps every dump a distinct object: retention is the bucket lifecycle
# rule's job (infra/backups.tf), not this script's.
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
key="${BACKUP_PREFIX}/$(date -u +%Y/%m)/carpool-${stamp}.dump"

# The dump is taken and checked inside the Postgres container, because that is
# where a pg_dump matching the server version lives. Connecting over the
# container's unix socket needs no password: the official image trusts local
# connections, so no credential is read, passed, or exported here.
#
# -Fc (custom format) rather than plain SQL: it is compressed, and pg_restore
# can read its table of contents, which is what makes the integrity check below
# possible without a database to restore into.
container_dump=/tmp/carpool-${stamp}.dump

log "dumping to container path ${container_dump}"
docker compose exec -T postgres sh -c '
  set -eu
  pg_dump -U carpool -d carpool -Fc -f "$1"
  # Parses the archive header and walks its table of contents. A truncated or
  # corrupt dump fails here, on the box, while the good one from last night is
  # still the newest object in the bucket -- rather than being discovered during
  # a restore, which is the worst possible moment to learn it.
  pg_restore --list "$1" > /dev/null
' sh "$container_dump" || fail "pg_dump or its integrity check failed"

staged="$(mktemp "/tmp/carpool-backup-${stamp}.XXXXXX")"
# Remove the staged copy however this script exits. It holds real participant
# data in the clear, so it must not outlive the upload.
trap 'rm -f "$staged"; docker compose exec -T postgres rm -f "$container_dump" >/dev/null 2>&1 || true' EXIT

docker compose exec -T postgres cat "$container_dump" > "$staged" \
  || fail "could not copy the dump off the container"

size="$(wc -c < "$staged")"
# A custom-format dump of even an empty schema is a few KB; anything smaller is
# a truncated copy, not a small database.
[ "$size" -ge 1024 ] || fail "dump is implausibly small (${size} bytes)"
log "staged ${size} bytes"

# --if-none-match '*' uploads only if the key does not already exist. Keys are
# timestamped above so a collision should be impossible; this turns "should be"
# into a refusal rather than a silent overwrite of a backup. It is also what
# lets the bucket later enforce create-only writes (review M1) with no change
# here.
#
# --checksum-algorithm SHA256 makes S3 verify what it received against a hash
# the CLI computes locally, so a corrupted upload is rejected by S3 instead of
# being stored as a valid-looking object.
log "uploading s3://${BACKUP_BUCKET}/${key}"
aws s3api put-object \
  --region "$AWS_REGION" \
  --bucket "$BACKUP_BUCKET" \
  --key "$key" \
  --body "$staged" \
  --if-none-match '*' \
  --checksum-algorithm SHA256 \
  --output text --query 'ETag' > /dev/null \
  || fail "upload of ${key} failed"

log "ok ${key} (${size} bytes)"
