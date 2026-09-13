#!/bin/bash
# scripts/backup_postgres.sh — PostgreSQL Backup مع PITR support
#
# المرجع: مراجعة Production Readiness — "PITR backups, WAL archiving"
#
# الميزات:
#   ١. pg_dump → custom format (مضغوط، parallel-safe)
#   ٢. WAL archiving (للـPITR — Point In Time Recovery)
#   ٣. logical retention only; physical/WAL retention requires a verified boundary
#   ٤. readable logical catalog / verified physical manifest; live restore still required
#   ٥. metrics لـPrometheus (نجاح/فشل + حجم)
#
# Usage:
#   ./backup_postgres.sh full          # full snapshot
#   ./backup_postgres.sh base          # physical PG16 base + manifest
#   ./backup_postgres.sh wal_archive <source> <segment>  # archive_command callback
#   ./backup_postgres.sh verify <file> # verify backup
#
# Cron suggestion:
#   0 2 * * *  /scripts/backup_postgres.sh full   # daily 2am full
#   WAL is archived by PostgreSQL archive_command, not by a periodic cron.

set -Eeuo pipefail

# ─── Config (env vars) ──────────────────────────────────────────

BACKUP_DIR="${BACKUP_DIR:-/var/backups/sahool}"
S3_BUCKET="${S3_BUCKET:-sahool-backups}"
S3_PREFIX="${S3_PREFIX:-postgres}"
RETENTION_DAYS_LOCAL="${RETENTION_DAYS_LOCAL:-7}"
RETENTION_DAYS_S3="${RETENTION_DAYS_S3:-30}"

# Postgres connection — **تعريفٌ واحد** يقرأ منه النسخُ الاحتياطيّ والاستعادة معاً.
# البيئةُ تَغلِب الافتراضَ كما كانت. (سببُ إخراجها إلى ملفٍّ واحد في رأس الملفّ نفسِه.)
# shellcheck source=lib/pg_conn_defaults.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/pg_conn_defaults.sh"
# PGPASSWORD يجب أن يُمرّر عبر env (لا في الـscript)

# Metrics endpoint (Prometheus pushgateway)
PUSHGATEWAY="${PUSHGATEWAY:-http://prometheus-pushgateway:9091}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_PREFIX="[backup-$TIMESTAMP]"

# ─── Helpers ────────────────────────────────────────────────────

log() { echo "$LOG_PREFIX $*" >&2; }

push_metric() {
  local name=$1 value=$2 labels=${3:-}
  # silent push — لا يجب أن يفشل الـbackup إن فشل الـmetrics
  if command -v curl &>/dev/null; then
    echo "${name}${labels:+{${labels}}} ${value}" \
      | curl -s --max-time 5 --data-binary @- \
        "${PUSHGATEWAY}/metrics/job/postgres_backup" \
      || true
  fi
}

ensure_dir() {
  mkdir -p "$BACKUP_DIR/full" "$BACKUP_DIR/base" "$BACKUP_DIR/wal" "$BACKUP_DIR/logs"
}

# ─── Backup operations ──────────────────────────────────────────

backup_full() {
  ensure_dir
  local outfile="$BACKUP_DIR/full/sahool_${TIMESTAMP}.dump"
  local start_time=$(date +%s)

  log "Starting full backup → $outfile"

  # pg_dump custom format (-Fc):
  #   - مضغوط (level 5 افتراضياً)
  #   - يدعم selective restore
  #   - parallel restore via pg_restore -j N
  if pg_dump \
      --format=custom \
      --compress=6 \
      --no-owner \
      --no-privileges \
      --verbose \
      --file="$outfile" \
      "$PGDATABASE" 2>"$BACKUP_DIR/logs/full_${TIMESTAMP}.log"; then

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local size_bytes=$(stat -c%s "$outfile")
    local size_mb=$((size_bytes / 1024 / 1024))

    log "✓ Backup complete: ${size_mb}MB in ${duration}s"

    # Verify integrity
    if pg_restore --list "$outfile" > /dev/null 2>&1; then
      log "✓ Archive catalog readable (a restore drill is still required)"
      push_metric "sahool_backup_size_bytes" "$size_bytes" 'type="full"'
      push_metric "sahool_backup_duration_seconds" "$duration" 'type="full"'

      # Upload to S3 (optional)
      if [[ -n "${AWS_ACCESS_KEY_ID:-}" ]] && command -v aws &>/dev/null; then
        log "Uploading to s3://${S3_BUCKET}/${S3_PREFIX}/full/"
        if aws s3 cp "$outfile" "s3://${S3_BUCKET}/${S3_PREFIX}/full/" \
            --storage-class STANDARD_IA \
            --metadata "timestamp=${TIMESTAMP},database=${PGDATABASE}"; then
          log "✓ Uploaded to S3"
          push_metric "sahool_backup_s3_upload_success" "1" 'type="full"'
        else
          log "✗ S3 upload failed"
          push_metric "sahool_backup_s3_upload_success" "0" 'type="full"'
        fi
      fi
    else
      log "✗ Integrity check FAILED"
      push_metric "sahool_backup_success" "0" 'type="full"'
      exit 1
    fi
  else
    log "✗ pg_dump failed (see logs)"
    push_metric "sahool_backup_success" "0" 'type="full"'
    exit 1
  fi
}

backup_wal_archive() {
  # WAL archiving للـPITR
  # Note: WAL archive_command يجب أن يكون مفعّلاً في postgresql.conf:
  #   archive_mode = on
  #   archive_command = '/scripts/backup_postgres.sh wal_archive %p %f'
  ensure_dir

  local wal_path="${1:-}"
  local wal_filename="${2:-}"

  if [[ -z "$wal_path" ]]; then
    # Manual run — لا شيء لأرشفته
    log "WAL archive mode: nothing to do (run via archive_command)"
    return 0
  fi

  if [[ ! "$wal_filename" =~ ^[0-9A-F]{24}(\.[0-9A-F]{8}\.backup)?$ && ! "$wal_filename" =~ ^[0-9A-F]{8}\.history$ ]]; then
    log "Invalid WAL archive filename"
    return 1
  fi
  local dest="$BACKUP_DIR/wal/$wal_filename"
  # Never overwrite a different archived segment with the same identity.
  if [[ -f "$dest" ]]; then
    cmp -s "$wal_path" "$dest" || return 1
  else
  local temporary
  temporary=$(mktemp "$BACKUP_DIR/wal/.${wal_filename}.XXXXXX")
  if ! cp -- "$wal_path" "$temporary" || ! sync -f "$temporary"; then
    rm -f -- "$temporary"
    return 1
  fi
  # Atomic create-if-absent also protects concurrent archiver invocations.
  if ln -- "$temporary" "$dest" 2>/dev/null; then
    rm -f -- "$temporary"
  else
    rm -f -- "$temporary"
    cmp -s "$wal_path" "$dest" || return 1
  fi
  sync -f "$BACKUP_DIR/wal"
  fi
  if [[ -n "${AWS_ACCESS_KEY_ID:-}" ]] && command -v aws &>/dev/null; then
    # Archive success must wait for the configured remote durability target.
    aws s3 cp "$dest" "s3://${S3_BUCKET}/${S3_PREFIX}/wal/" --storage-class STANDARD_IA --quiet
  fi
  push_metric "sahool_wal_archive_success" "1"

}

# ─── Verification ───────────────────────────────────────────────

verify_backup() {
  local file="${1:?backup file required}"
  if [[ ! -f "$file" ]]; then
    log "✗ File not found: $file"
    exit 1
  fi

  log "Verifying: $file"
  if pg_restore --list "$file" > /dev/null 2>&1; then
    local table_count
    table_count=$(pg_restore --list "$file" | awk '/TABLE DATA/{n++} END {print n+0}')
    log "✓ Archive catalog readable: $table_count tables; restore not yet verified."
    return 0
  else
    log "✗ Backup CORRUPTED"
    exit 1
  fi
}

# ─── Retention (cleanup) ────────────────────────────────────────

cleanup_old() {
  log "Cleaning up backups older than ${RETENTION_DAYS_LOCAL} days locally"
  [[ "$RETENTION_DAYS_LOCAL" =~ ^[0-9]+$ ]] || { log "Invalid retention days"; return 1; }
  ensure_dir
  local deleted
  deleted=$(find "$BACKUP_DIR/full" -mindepth 1 -maxdepth 1 -type f -name 'sahool_*.dump' \
    -mtime +"$RETENTION_DAYS_LOCAL" -delete -print | wc -l)
  log "Deleted $deleted old local logical backups"
  # WAL age alone cannot establish whether a retained physical base needs it.
  # Prune only after a verified restore establishes the oldest required segment.
  log "WAL and physical bases retained; prune from a verified restore boundary"

  # S3 cleanup (delegate to S3 lifecycle policy in production)
  log "S3 retention managed by lifecycle policy (${RETENTION_DAYS_S3} days)"
}

# ─── Restore (documentation only — destructive) ─────────────────

show_restore_help() {
  cat <<'EOF'
Logical restore (custom-format pg_dump; not PITR):
  ./scripts/restore_postgres.sh /var/backups/sahool/full/sahool_TIMESTAMP.dump --dry-run
  ./scripts/restore_postgres.sh /var/backups/sahool/full/sahool_TIMESTAMP.dump

PostgreSQL 16 PITR requires a PHYSICAL base plus continuous archived WAL:
  ./scripts/backup_postgres.sh base
  ./scripts/restore_postgres.sh --pitr /var/backups/sahool/base/base_TIMESTAMP \
    --target-dir /var/lib/postgresql/recovery-drill \
    --wal-dir /var/backups/sahool/wal --target-time '2026-09-13T10:00:00Z' --dry-run
Remove --dry-run to prepare a NEW EMPTY target, then start an isolated PostgreSQL
16 instance there. recovery.signal and PostgreSQL 16 recovery settings are written
by the preparation command. It does not start PostgreSQL or replace a live volume.

A readable pg_restore catalog is not a restore proof. Check rows, roles, RLS,
application queries, recovery target reached, and measured RPO/RTO in a drill.
See docs/runbooks/POSTGRES_RECOVERY.md for WAL provisioning and storage coverage.

EOF
}

backup_base() {
  ensure_dir
  local destination="$BACKUP_DIR/base/base_${TIMESTAMP}"
  local temporary="${destination}.partial"
  # This local layout supports the default tablespaces only. External tablespace
  # mappings must be designed before allowing pg_basebackup to write their paths.
  if [[ "$(psql -X -Atqc "SELECT count(*) FROM pg_tablespace WHERE spcname NOT IN ('pg_default','pg_global')")" != 0 ]]; then
    log "External tablespaces require an explicit backup mapping"
    return 1
  fi
  [[ ! -e "$temporary" && ! -e "$destination" ]] || { log "Backup destination exists"; return 1; }
  pg_basebackup --pgdata="$temporary" --format=plain --wal-method=stream \
    --checkpoint=fast --manifest-checksums=SHA256
  pg_verifybackup "$temporary"
  mv -- "$temporary" "$destination"
  log "Physical base verified: $destination (live restore not yet measured)"
  push_metric "sahool_backup_success" "1" 'type="base"'
}

# ─── Main ───────────────────────────────────────────────────────

# A failed final stage must not leave a success metric for the overall job.
case "${1:-help}" in
  full|base) BACKUP_KIND="$1"; trap 'push_metric "sahool_backup_success" "0" "type=\"$BACKUP_KIND\""' ERR ;;
esac

case "${1:-help}" in
  full)
    backup_full
    cleanup_old
    push_metric "sahool_backup_success" "1" 'type="full"'
    ;;
  base)
    backup_base
    ;;
  wal_archive)
    backup_wal_archive "${2:-}" "${3:-}"
    ;;
  verify)
    verify_backup "${2:-}"
    ;;
  cleanup)
    cleanup_old
    ;;
  restore-help)
    show_restore_help
    ;;
  *)
    echo "Usage: $0 {full|base|wal_archive <path> <filename>|verify <file>|cleanup|restore-help}"
    exit 1
    ;;
esac
