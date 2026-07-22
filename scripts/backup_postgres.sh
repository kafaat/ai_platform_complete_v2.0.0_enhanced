#!/bin/bash
# scripts/backup_postgres.sh — PostgreSQL Backup مع PITR support
#
# المرجع: مراجعة Production Readiness — "PITR backups, WAL archiving"
# حزمة 72 ساعة (DB-P0-04): تصحيح الافتراضيّات إلى خدمة compose الفعليّة
# (sahool-postgres) ودور التهيئة الفعليّ (sahool_user) — الافتراضيان القديمان
# (sahool-postgis/postgres) كانا يجعلان التشغيل بلا env يفشل أو يصيب هدفًا خاطئًا.
#
# الميزات:
#   ١. pg_dump → custom format (مضغوط، parallel-safe)
#   ٢. WAL archiving (للـPITR — Point In Time Recovery)
#   ٣. retention: ٧ days local + ٣٠ days S3
#   ٤. integrity check بعد كل backup
#   ٥. metrics لـPrometheus (نجاح/فشل + حجم)
#
# Usage:
#   ./backup_postgres.sh full          # full snapshot
#   ./backup_postgres.sh wal_archive   # WAL segments only
#   ./backup_postgres.sh verify <file> # verify backup
#
# Cron suggestion:
#   0 2 * * *  /scripts/backup_postgres.sh full   # daily 2am full
#   */15 * * * /scripts/backup_postgres.sh wal_archive  # every 15min WAL

set -euo pipefail

# ─── Config (env vars) ──────────────────────────────────────────

BACKUP_DIR="${BACKUP_DIR:-/var/backups/sahool}"
S3_BUCKET="${S3_BUCKET:-sahool-backups}"
S3_PREFIX="${S3_PREFIX:-postgres}"
RETENTION_DAYS_LOCAL="${RETENTION_DAYS_LOCAL:-7}"
RETENTION_DAYS_S3="${RETENTION_DAYS_S3:-30}"

# Postgres connection (from env)
PGHOST="${PGHOST:-sahool-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-sahool_user}"
PGDATABASE="${PGDATABASE:-sahool}"
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
  mkdir -p "$BACKUP_DIR/full" "$BACKUP_DIR/wal" "$BACKUP_DIR/logs"
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
      log "✓ Integrity check passed"
      push_metric "sahool_backup_success" "1" 'type="full"'
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
  #   archive_command = '/scripts/backup_postgres.sh wal_archive_one %p %f'
  ensure_dir

  local wal_path="${1:-}"
  local wal_filename="${2:-}"

  if [[ -z "$wal_path" ]]; then
    # Manual run — لا شيء لأرشفته
    log "WAL archive mode: nothing to do (run via archive_command)"
    return 0
  fi

  local dest="$BACKUP_DIR/wal/$wal_filename"
  if cp "$wal_path" "$dest" && [[ -f "$dest" ]]; then
    push_metric "sahool_wal_archive_success" "1"
    # S3 backup (async, non-blocking)
    if [[ -n "${AWS_ACCESS_KEY_ID:-}" ]] && command -v aws &>/dev/null; then
      aws s3 cp "$dest" "s3://${S3_BUCKET}/${S3_PREFIX}/wal/" \
        --storage-class STANDARD_IA \
        --quiet &
    fi
    return 0
  else
    push_metric "sahool_wal_archive_success" "0"
    return 1
  fi
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
    local table_count=$(pg_restore --list "$file" | grep -c "TABLE DATA" || echo 0)
    log "✓ Backup valid. Contains $table_count tables."
    return 0
  else
    log "✗ Backup CORRUPTED"
    exit 1
  fi
}

# ─── Retention (cleanup) ────────────────────────────────────────

cleanup_old() {
  log "Cleaning up backups older than ${RETENTION_DAYS_LOCAL} days locally"
  find "$BACKUP_DIR/full" -name "sahool_*.dump" \
    -mtime +${RETENTION_DAYS_LOCAL} -delete -print 2>/dev/null \
    | wc -l | xargs -I{} log "Deleted {} old local backups"

  find "$BACKUP_DIR/wal" -name "*" \
    -mtime +${RETENTION_DAYS_LOCAL} -delete 2>/dev/null || true

  # S3 cleanup (delegate to S3 lifecycle policy in production)
  log "S3 retention managed by lifecycle policy (${RETENTION_DAYS_S3} days)"
}

# ─── Restore (documentation only — destructive) ─────────────────

show_restore_help() {
  cat <<'EOF'
RESTORE PROCEDURES (run manually with care):

  ١. Full restore (last backup):
     gunzip -c /var/backups/sahool/full/sahool_LATEST.dump.gz | \
       pg_restore --dbname=sahool --clean --if-exists --verbose

  ٢. Selective restore (one table):
     pg_restore --dbname=sahool \
       --table=field_boundaries \
       /var/backups/sahool/full/sahool_TIMESTAMP.dump

  ٣. PITR (Point In Time Recovery):
     # Stop postgres
     # Restore base backup
     pg_restore --dbname=sahool /var/backups/sahool/full/sahool_BASE.dump
     # Configure recovery.conf:
     #   restore_command = 'cp /var/backups/sahool/wal/%f %p'
     #   recovery_target_time = '2026-06-03 14:30:00 UTC'
     # Start postgres → it replays WAL until target time

  ٤. Verify before relying:
     ./backup_postgres.sh verify /path/to/backup.dump

REMEMBER:
  - Test restores monthly (drill)
  - Never restore to production without dry-run first
  - WAL retention must cover RPO (recovery point objective)
EOF
}

# ─── Main ───────────────────────────────────────────────────────

case "${1:-help}" in
  full)
    backup_full
    cleanup_old
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
    echo "Usage: $0 {full|wal_archive|verify <file>|cleanup|restore-help}"
    exit 1
    ;;
esac
