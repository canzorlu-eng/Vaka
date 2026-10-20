#!/usr/bin/env bash
# Logical backup of the Vaka database: pg_dump (custom format, compressed) -> verify -> upload -> prune.
#
# Required env:  DATABASE_URL
# Target (one of):
#   BACKUP_TARGET=file:///abs/dir            local directory (tests / drills)
#   BACKUP_S3_BUCKET [+ BACKUP_S3_ENDPOINT]  S3-compatible storage (Cloudflare R2, Backblaze B2, AWS S3);
#                                            credentials via AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
# Optional env:  BACKUP_PREFIX (default vaka/<APP_ENV>), BACKUP_KEEP_DAILY (14), BACKUP_KEEP_WEEKLY (8),
#                BACKUP_WEEKLY_DOW (7 = Sunday, ISO), ALERT_WEBHOOK_URL, AWS_DEFAULT_REGION (default auto)
# Layout under the target:  <prefix>/daily/vaka-<UTC stamp>.dump(+.counts)  and  <prefix>/weekly/... (copy made on Sundays)
# Never prints DATABASE_URL or credentials. Exits non-zero (and posts to ALERT_WEBHOOK_URL) on any failure.
set -Eeuo pipefail
set +x

KEEP_DAILY="${BACKUP_KEEP_DAILY:-14}"
KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-8}"
WEEKLY_DOW="${BACKUP_WEEKLY_DOW:-7}"
PREFIX="${BACKUP_PREFIX:-vaka/${APP_ENV:-env}}"
PREFIX="${PREFIX#/}"; PREFIX="${PREFIX%/}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-auto}"
STEP="init"
WORK="$(mktemp -d)"
log() { printf '%s [backup] %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

alert() {
  [[ -n "${ALERT_WEBHOOK_URL:-}" ]] || return 0
  local text="[Vaka/${APP_ENV:-?}] BACKUP FAILED at step '${STEP}' (host $(hostname)). See cron job logs."
  curl -fsS -m 10 -H 'Content-Type: application/json' \
    -d "{\"text\":\"${text}\",\"content\":\"${text}\"}" "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 || true
}
on_err() { local rc=$?; log "FAILED at step '${STEP}' (exit ${rc})"; alert; exit "${rc:-1}"; }
cleanup() { rm -rf "$WORK"; }
trap on_err ERR
trap cleanup EXIT

[[ -n "${DATABASE_URL:-}" ]] || { STEP="config"; log "DATABASE_URL is not set"; false; }

# ---------------------------------------------------------------- storage backend
TARGET_KIND=""; LOCAL_DIR=""
if [[ "${BACKUP_TARGET:-}" == file://* ]]; then
  TARGET_KIND=file; LOCAL_DIR="${BACKUP_TARGET#file://}"; mkdir -p "$LOCAL_DIR"
elif [[ -n "${BACKUP_S3_BUCKET:-}" ]]; then
  TARGET_KIND=s3
  AWS_ARGS=(); [[ -z "${BACKUP_S3_ENDPOINT:-}" ]] || AWS_ARGS+=(--endpoint-url "$BACKUP_S3_ENDPOINT")
else
  STEP="config"; log "set BACKUP_TARGET=file:///dir or BACKUP_S3_BUCKET"; false
fi

t_put()  { # local_file key
  if [[ $TARGET_KIND == file ]]; then mkdir -p "$LOCAL_DIR/$(dirname "$2")"; cp "$1" "$LOCAL_DIR/$2"
  else aws "${AWS_ARGS[@]}" s3 cp --only-show-errors "$1" "s3://${BACKUP_S3_BUCKET}/$2"; fi; }
t_list() { # prefix -> object names (base names), one per line
  if [[ $TARGET_KIND == file ]]; then ls -1 "$LOCAL_DIR/$1" 2>/dev/null || true
  else aws "${AWS_ARGS[@]}" s3 ls "s3://${BACKUP_S3_BUCKET}/$1/" 2>/dev/null | awk '{print $4}' || true; fi; }
t_rm()   { # key
  if [[ $TARGET_KIND == file ]]; then rm -f "$LOCAL_DIR/$1"
  else aws "${AWS_ARGS[@]}" s3 rm --only-show-errors "s3://${BACKUP_S3_BUCKET}/$1"; fi; }

# ---------------------------------------------------------------- dump
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="vaka-${STAMP}.dump"
STEP="pg_dump"
log "dumping database to ${NAME}"
START=$SECONDS
pg_dump --format=custom --compress=6 --no-owner --no-privileges --dbname="$DATABASE_URL" --file="$WORK/$NAME"

STEP="verify"
pg_restore --list "$WORK/$NAME" >/dev/null           # fails on a truncated/corrupt archive
SIZE=$(stat -c %s "$WORK/$NAME")
[[ $SIZE -gt 1024 ]] || { log "dump suspiciously small (${SIZE} bytes)"; false; }
( cd "$WORK" && sha256sum "$NAME" > "$NAME.sha256" )

# Row counts at dump time (approximate: taken right after the dump, not in the same snapshot). Used by restore_test.sh.
STEP="counts"
{
  for t in users case_sessions case_reports; do
    printf '%s=%s\n' "$t" "$(psql "$DATABASE_URL" -X -At -c "SELECT count(*) FROM ${t}" 2>/dev/null || echo -1)"
  done
} > "$WORK/$NAME.counts"

STEP="upload"
for f in "$NAME" "$NAME.sha256" "$NAME.counts"; do t_put "$WORK/$f" "$PREFIX/daily/$f"; done
if [[ "$(date -u +%u)" == "$WEEKLY_DOW" ]]; then
  for f in "$NAME" "$NAME.sha256" "$NAME.counts"; do t_put "$WORK/$f" "$PREFIX/weekly/$f"; done
  log "weekly copy stored"
fi

# ---------------------------------------------------------------- retention
prune() { # subdir keep
  STEP="prune-$1"
  local old
  old="$(t_list "$PREFIX/$1" | grep -E '^vaka-[0-9TZ]+\.dump$' | sort -r | tail -n +"$(( $2 + 1 ))" || true)"
  [[ -z "$old" ]] && return 0
  while read -r f; do
    [[ -n "$f" ]] || continue
    for ext in "" .sha256 .counts; do t_rm "$PREFIX/$1/$f$ext"; done
    log "pruned $1/$f"
  done <<< "$old"
}
prune daily "$KEEP_DAILY"
prune weekly "$KEEP_WEEKLY"

STEP="done"
log "OK ${NAME} size=${SIZE}B duration=$(( SECONDS - START ))s counts: $(tr '\n' ' ' < "$WORK/$NAME.counts")"
