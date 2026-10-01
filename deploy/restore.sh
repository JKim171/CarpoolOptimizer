#!/bin/bash
# Reading the backups back. Three modes, because "we have backups" and "we can
# restore" are different claims and only the second one matters
# (docs/roadmap.md week 6: rehearse one restore).
#
#   restore.sh --list                      what is in the bucket, newest last
#   restore.sh --rehearse [KEY|--latest]   restore into a scratch database and
#                                          report what came back. Touches
#                                          nothing the app uses. This is the
#                                          default, and the one to run on a
#                                          schedule.
#   restore.sh --into-production KEY       the real recovery path. Replaces the
#                                          live database. Refuses without
#                                          --i-mean-it.
#
# Ships in the image's deploy/ directory alongside backup.sh, so the restore
# tool and the dump format it reads always come from the same build.
set -euo pipefail
umask 077

: "${APP_DIR:=/opt/carpool}"
: "${BACKUP_BUCKET:?BACKUP_BUCKET must name the bucket to read}"
: "${BACKUP_PREFIX:=dumps}"
: "${AWS_REGION:=us-east-1}"
# Deliberately not "carpool_test": this name should never collide with
# something a human made for another purpose.
: "${REHEARSE_DB:=carpool_restore_check}"

# Progress goes to stderr, so that stdout carries only data: the listing in
# --list and the row counts below. journald records both streams either way.
log() { printf '%s restore: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
fail() { log "FAILED: $*"; exit 1; }

cd "$APP_DIR"

# Paths to delete on the way out, whatever the exit status. These are globals on
# purpose: the trap runs after fetch_to_container has returned, so anything
# function-local would be out of scope by then -- and under `set -u` the
# cleanup would fail silently, leaving a plaintext copy of real addresses on the
# box. That is the one failure here with a privacy consequence.
CLEANUP_HOST=""
CLEANUP_CONTAINER=""
cleanup() {
  [ -n "$CLEANUP_HOST" ] && rm -f "$CLEANUP_HOST"
  [ -n "$CLEANUP_CONTAINER" ] &&
    docker compose exec -T postgres rm -f "$CLEANUP_CONTAINER" >/dev/null 2>&1
  return 0
}
trap cleanup EXIT

psql_super() { docker compose exec -T postgres psql -U carpool -d postgres -v ON_ERROR_STOP=1 "$@"; }

list_keys() {
  aws s3api list-objects-v2 \
    --region "$AWS_REGION" --bucket "$BACKUP_BUCKET" --prefix "${BACKUP_PREFIX}/" \
    --query 'sort_by(Contents,&LastModified)[].[LastModified,Size,Key]' --output text
}

latest_key() {
  aws s3api list-objects-v2 \
    --region "$AWS_REGION" --bucket "$BACKUP_BUCKET" --prefix "${BACKUP_PREFIX}/" \
    --query 'sort_by(Contents,&LastModified)[-1].Key' --output text
}

# Pull KEY out of the bucket, check it is a readable archive, and leave it at a
# path inside the Postgres container, which it reports in FETCHED.
#
# It reports through a global rather than stdout because a `$(...)` capture runs
# the function in a subshell, and the cleanup paths it registers would die with
# that subshell -- leaving a plaintext dump on the box. Call it directly.
FETCHED=""
fetch_to_container() {
  local key="$1" local_file container_file
  local_file="$(mktemp /tmp/carpool-restore.XXXXXX)"
  container_file="/tmp/$(basename "$key")"
  # Register both before anything is written to them, so a failure midway
  # through still cleans up. The downloaded dump is real participant data in
  # the clear and must not outlive this script in either place.
  CLEANUP_HOST="$local_file"
  CLEANUP_CONTAINER="$container_file"

  log "fetching s3://${BACKUP_BUCKET}/${key}"
  aws s3api get-object --region "$AWS_REGION" --bucket "$BACKUP_BUCKET" \
    --key "$key" "$local_file" --output text --query 'ContentLength' > /dev/null \
    || fail "could not download ${key}"

  docker compose cp "$local_file" "postgres:${container_file}" > /dev/null \
    || fail "could not copy the dump into the postgres container"

  docker compose exec -T postgres pg_restore --list "$container_file" > /dev/null \
    || fail "${key} is not a readable pg_dump archive"

  FETCHED="$container_file"
}

# What actually came back. A restore that reports "success" having created an
# empty schema is the failure this is here to catch, so count rows rather than
# trusting pg_restore's exit status.
report_contents() {
  local db="$1"
  log "row counts in ${db}:"
  docker compose exec -T postgres psql -U carpool -d "$db" -At -F $'\t' -c "
    select relname, n_live_tup
      from pg_stat_user_tables
     order by relname;
  " | awk -F '\t' '{ printf "    %-28s %s\n", $1, $2 }'
  # pg_stat_user_tables is an estimate maintained by ANALYZE, so anchor the
  # headline number on an exact count of the table that matters most.
  local participants
  participants="$(docker compose exec -T postgres psql -U carpool -d "$db" -At \
    -c 'select count(*) from participants;' 2>/dev/null || echo '?')"
  log "exact participants row count: ${participants}"
}

mode="--rehearse"
key=""
confirm="no"
while [ $# -gt 0 ]; do
  case "$1" in
    --list | --rehearse | --into-production) mode="$1" ;;
    --latest) key="" ;;
    --i-mean-it) confirm="yes" ;;
    -*) fail "unknown option $1" ;;
    *) key="$1" ;;
  esac
  shift
done

case "$mode" in
  --list)
    log "dumps in s3://${BACKUP_BUCKET}/${BACKUP_PREFIX}/ (oldest first)"
    list_keys
    ;;

  --rehearse)
    [ -n "$key" ] || key="$(latest_key)"
    [ -n "$key" ] && [ "$key" != "None" ] || fail "no dumps found in the bucket"
    fetch_to_container "$key"

    log "restoring ${key} into scratch database ${REHEARSE_DB}"
    psql_super -c "drop database if exists ${REHEARSE_DB};" > /dev/null
    psql_super -c "create database ${REHEARSE_DB};" > /dev/null
    # --no-owner/--no-privileges: the scratch database only has to prove the
    # data and schema survived, and role grants from the source would fail here
    # for reasons that say nothing about the dump.
    docker compose exec -T postgres pg_restore \
      -U carpool -d "$REHEARSE_DB" --no-owner --no-privileges "$FETCHED" \
      || fail "pg_restore into ${REHEARSE_DB} failed"

    report_contents "$REHEARSE_DB"

    if [ "$confirm" = "yes" ]; then
      log "keeping ${REHEARSE_DB} for inspection (--i-mean-it given); drop it when done"
    else
      psql_super -c "drop database ${REHEARSE_DB};" > /dev/null
      log "dropped ${REHEARSE_DB} -- a second copy of real addresses should not linger on the box"
    fi
    log "rehearsal OK: ${key} restores"
    ;;

  --into-production)
    [ -n "$key" ] || fail "--into-production needs an explicit key; refusing to guess"
    [ "$confirm" = "yes" ] || fail "this REPLACES the live database. Re-run with --i-mean-it if that is what you want."
    fetch_to_container "$key"

    # The api holds a connection pool open; dropping the database under it
    # fails, and leaving it up during the restore would let requests read a
    # half-restored schema.
    log "stopping api"
    docker compose stop api

    log "replacing the live database from ${key}"
    psql_super -c "drop database if exists carpool;" > /dev/null
    psql_super -c "create database carpool;" > /dev/null
    docker compose exec -T postgres pg_restore \
      -U carpool -d carpool --no-owner --no-privileges "$FETCHED" \
      || { log "pg_restore FAILED -- api left stopped on purpose, the database is half-restored"; exit 1; }

    report_contents carpool

    log "starting api"
    docker compose up -d api
    log "restore complete. Check /readyz before announcing it."
    ;;
esac
