#!/usr/bin/env bash
# Restore drill: restore a Vaka dump into a SCRATCH database and run sanity checks. Never writes to the source DB.
#
# Usage: restore_test.sh [dump-file]       (no argument: download the LATEST daily dump from the backup target)
# Env:   RESTORE_ADMIN_URL  server to create the scratch DB on (default: DATABASE_URL). Only `CREATE DATABASE` /
#                           `DROP DATABASE` of the generated scratch name are issued against it. Needs CREATEDB; if the
#                           app role lacks it (managed Postgres), point this at a throw-away Postgres instead.
#        BACKUP_TARGET / BACKUP_S3_BUCKET / BACKUP_S3_ENDPOINT / BACKUP_PREFIX / AWS_* : same as backup.sh
#        RESTORE_MAX_AGE_HOURS (default 36): fail if the latest dump is older than this (catches silently failing cron)
#        ALERT_WEBHOOK_URL: failure notification
# Exit 0 only if restore + all sanity checks pass. Never prints credentials.
set -Eeuo pipefail
set +x

ADMIN_URL="${RESTORE_ADMIN_URL:-${DATABASE_URL:-}}"
PREFIX="${BACKUP_PREFIX:-vaka/${APP_ENV:-env}}"; PREFIX="${PREFIX#/}"; PREFIX="${PREFIX%/}"
MAX_AGE_H="${RESTORE_MAX_AGE_HOURS:-36}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-auto}"
STEP="init"; SCRATCH=""; WORK="$(mktemp -d)"; START=$SECONDS
log() { printf '%s [restore-test] %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

alert() {
  [[ -n "${ALERT_WEBHOOK_URL:-}" ]] || return 0
  local text="[Vaka/${APP_ENV:-?}] RESTORE TEST FAILED at step '${STEP}'. See cron job logs."
  curl -fsS -m 10 -H 'Content-Type: application/json' \
    -d "{\"text\":\"${text}\",\"content\":\"${text}\"}" "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 || true
}
drop_scratch() {
  [[ -n "$SCRATCH" ]] && psql "$ADMIN_URL" -X -q -c "DROP DATABASE IF EXISTS \"$SCRATCH\" WITH (FORCE)" >/dev/null 2>&1 || true
}
on_err() { local rc=$?; log "FAILED at step '${STEP}' (exit ${rc})"; trap - EXIT; drop_scratch; rm -rf "$WORK"; alert; exit "${rc:-1}"; }
cleanup() { drop_scratch; rm -rf "$WORK"; }
trap on_err ERR
trap cleanup EXIT

[[ -n "$ADMIN_URL" ]] || { STEP="config"; log "DATABASE_URL (or RESTORE_ADMIN_URL) is not set"; false; }

url_with_db() { # url dbname -> same server/credentials, different database (query string preserved)
  local base="${1%%\?*}" q=""; [[ "$1" == *\?* ]] && q="?${1#*\?}"
  printf '%s/%s%s' "${base%/*}" "$2" "$q"
}

# ---------------------------------------------------------------- locate the dump
DUMP="${1:-}"; COUNTS_FILE=""
if [[ -z "$DUMP" ]]; then
  STEP="fetch-latest"
  if [[ "${BACKUP_TARGET:-}" == file://* ]]; then
    dir="${BACKUP_TARGET#file://}/$PREFIX/daily"
    latest="$(ls -1 "$dir" 2>/dev/null | grep -E '^vaka-[0-9TZ]+\.dump$' | sort | tail -n 1 || true)"
    [[ -n "$latest" ]] || { log "no dumps found in $dir"; false; }
    cp "$dir/$latest" "$WORK/$latest"; cp "$dir/$latest.counts" "$WORK/$latest.counts" 2>/dev/null || true
    [[ ! -f "$dir/$latest.sha256" ]] || cp "$dir/$latest.sha256" "$WORK/"
  elif [[ -n "${BACKUP_S3_BUCKET:-}" ]]; then
    AWS_ARGS=(); [[ -z "${BACKUP_S3_ENDPOINT:-}" ]] || AWS_ARGS+=(--endpoint-url "$BACKUP_S3_ENDPOINT")
    latest="$(aws "${AWS_ARGS[@]}" s3 ls "s3://${BACKUP_S3_BUCKET}/$PREFIX/daily/" | awk '{print $4}' \
              | grep -E '^vaka-[0-9TZ]+\.dump$' | sort | tail -n 1 || true)"
    [[ -n "$latest" ]] || { log "no dumps found under $PREFIX/daily"; false; }
    for ext in "" .sha256 .counts; do
      aws "${AWS_ARGS[@]}" s3 cp --only-show-errors "s3://${BACKUP_S3_BUCKET}/$PREFIX/daily/$latest$ext" "$WORK/$latest$ext" 2>/dev/null || true
    done
  else
    log "pass a dump file or set BACKUP_TARGET / BACKUP_S3_BUCKET"; false
  fi
  DUMP="$WORK/$latest"
  stamp="${latest#vaka-}"; stamp="${stamp%.dump}"
  dump_epoch="$(date -u -d "${stamp:0:4}-${stamp:4:2}-${stamp:6:2} ${stamp:9:2}:${stamp:11:2}:${stamp:13:2}" +%s)"
  age_h=$(( ( $(date -u +%s) - dump_epoch ) / 3600 ))
  log "latest dump: $latest (age ${age_h}h)"
  [[ $age_h -le $MAX_AGE_H ]] || { STEP="freshness"; log "latest dump is older than ${MAX_AGE_H}h: the backup job is not running"; false; }
else
  [[ -f "$DUMP" ]] || { STEP="config"; log "file not found: $DUMP"; false; }
  log "using local dump: $(basename "$DUMP")"
fi
[[ ! -f "$DUMP.counts" ]] || COUNTS_FILE="$DUMP.counts"
if [[ -f "$DUMP.sha256" ]]; then
  STEP="checksum"; ( cd "$(dirname "$DUMP")" && sha256sum -c --status "$(basename "$DUMP").sha256" ); log "sha256 OK"
fi

# ---------------------------------------------------------------- restore into scratch DB
STEP="create-scratch"
SCRATCH="vaka_restore_test_$(date -u +%Y%m%d%H%M%S)_$RANDOM"
psql "$ADMIN_URL" -X -q -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$SCRATCH\"" >/dev/null
SCRATCH_URL="$(url_with_db "$ADMIN_URL" "$SCRATCH")"

STEP="pg_restore"
R0=$SECONDS
pg_restore --no-owner --no-privileges --exit-on-error --dbname="$SCRATCH_URL" "$DUMP"
RESTORE_S=$(( SECONDS - R0 ))

# ---------------------------------------------------------------- sanity checks
q() { psql "$SCRATCH_URL" -X -At -v ON_ERROR_STOP=1 -c "$1"; }
STEP="sanity-alembic"
VERSION="$(q "SELECT version_num FROM alembic_version")"
[[ -n "$VERSION" ]] || { log "alembic_version is empty"; false; }

STEP="sanity-counts"
declare -A ROWS
for t in users case_sessions case_reports; do
  ROWS[$t]="$(q "SELECT count(*) FROM $t")"
done
OTHER=""
for t in auth_sessions ai_cases jobs llm_usage subscriptions payment_events; do OTHER+="$t=$(q "SELECT count(*) FROM $t") "; done

STEP="sanity-constraints"
NOTVALID="$(q "SELECT count(*) FROM pg_constraint WHERE NOT convalidated")"
ORPHANS="$(q "SELECT (SELECT count(*) FROM case_sessions s LEFT JOIN users u ON u.id = s.user_id WHERE u.id IS NULL)
                    + (SELECT count(*) FROM case_reports r LEFT JOIN case_sessions s ON s.id = r.session_id WHERE s.id IS NULL)
                    + (SELECT count(*) FROM auth_sessions a LEFT JOIN users u ON u.id = a.user_id WHERE u.id IS NULL)")"
[[ "$NOTVALID" == "0" ]] || { log "$NOTVALID constraint(s) not validated"; false; }
[[ "$ORPHANS" == "0" ]] || { log "$ORPHANS orphaned row(s) (FK violation)"; false; }
q "SELECT 1 FROM pg_indexes WHERE indexname = 'users_email_lower_key'" | grep -q 1 || { log "expected index missing"; false; }

# Compare with the counts recorded by backup.sh (informational; the app keeps writing during the dump).
if [[ -n "$COUNTS_FILE" ]]; then
  STEP="sanity-compare"
  while IFS='=' read -r t n; do
    [[ -n "$t" ]] || continue
    log "  recorded at dump time: $t=$n  restored: ${ROWS[$t]:-?}"
    if [[ "$n" -gt 0 && "${ROWS[$t]:-0}" -eq 0 ]]; then log "table $t restored EMPTY"; false; fi
  done < "$COUNTS_FILE"
fi

STEP="done"
log "OK schema=${VERSION} restore=${RESTORE_S}s total=$(( SECONDS - START ))s rows: users=${ROWS[users]} case_sessions=${ROWS[case_sessions]} case_reports=${ROWS[case_reports]} | ${OTHER:-}"
