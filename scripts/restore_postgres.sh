#!/bin/bash
# scripts/restore_postgres.sh — استعادة PostgreSQL من نسخة backup_postgres.sh
#
# مكمّل لـbackup_postgres.sh (الذي يحوي إرشادات الاستعادة فقط، لا سكربتاً قابلاً للتشغيل).
#
# الميزات:
#   ١. استعادة كاملة من ملفّ custom-format (pg_restore)
#   ٢. استعادة انتقائيّة لجدول واحد (--table)
#   ٣. فحص سلامة النسخة قبل الاستعادة (يرفض الملفّ التالف)
#   ٤. تأكيد تفاعلي قبل الكتابة فوق قاعدة موجودة (حماية)
#   ٥. dry-run لعرض ما سيُستعاد دون تنفيذ
#
# الاستخدام:
#   ./restore_postgres.sh <backup_file>                    # استعادة كاملة (بتأكيد)
#   ./restore_postgres.sh <backup_file> --table soil_readings  # جدول واحد
#   ./restore_postgres.sh <backup_file> --dry-run          # عرض دون تنفيذ
#   ./restore_postgres.sh <backup_file> --force            # بلا تأكيد (للأتمتة)
#
# ⚠ تحذير: الاستعادة الكاملة تكتب فوق البيانات الحاليّة (--clean --if-exists).
#   اعمل نسخة احتياطيّة قبل الاستعادة في الإنتاج.

set -euo pipefail

# ─── Config ────────────────────────────────────────────────────
#
# **كان هنا جدولٌ ثانٍ يقول عن نفسه «نفس قيم `backup_postgres.sh`» — ولم يكن.**
# كان يقصد `sahool-postgis`/`postgres`، ولا وجودَ لذلك المضيف في
# `docker-compose.v9.yml`؛ فالاستعادةُ كانت تُوجَّه إلى مضيفٍ ودورٍ معدومين، في
# اللحظة الوحيدة التي لا تحتمل خطأً. والتفصيل في رأس الملفّ المصدر.
#
# shellcheck source=lib/pg_conn_defaults.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/pg_conn_defaults.sh"
# PGPASSWORD يُمرّر عبر env (لا في السكربت)

PARALLEL_JOBS="${PARALLEL_JOBS:-4}"
# Majors this repository deploys: Compose v9 runs postgis/postgis:15-3.4, the evidence
# lab runs 16-3.4. A physical base can only be recovered by a server of the SAME major.
SUPPORTED_PG_MAJORS="${SUPPORTED_PG_MAJORS:-15 16}"

# ─── ألوان للمخرجات ────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[restore]${NC} $*"; }
warn() { echo -e "${YELLOW}[restore]${NC} $*"; }
err()  { echo -e "${RED}[restore]${NC} $*" >&2; }

prepare_pitr() {
    local base="${1:?physical base directory required}" target="" wal="" target_time="" dry=0
    shift
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --target-dir) target="${2:?target directory required}"; shift 2 ;;
            --wal-dir) wal="${2:?WAL directory required}"; shift 2 ;;
            --target-time) target_time="${2:?target time required}"; shift 2 ;;
            --dry-run) dry=1; shift ;;
            *) err "Unknown PITR argument: $1"; return 1 ;;
        esac
    done
    [[ -f "$base/backup_manifest" && -f "$base/PG_VERSION" ]] || { err "A physical pg_basebackup directory is required"; return 1; }
    local base_major recovery_major
    base_major="$(tr -d '[:space:]' < "$base/PG_VERSION")"
    # A hardcoded "16" rejected every base taken from the deployed Compose database
    # (PostgreSQL 15) before recovery could begin (Copilot on #997). The base major must
    # be one this repository deploys, and must equal the major of the server that will
    # replay it: RECOVERY_PG_MAJOR when the operator names it, else the `postgres`
    # binary on PATH when one exists. Neither present ⇒ the operator is told to start
    # a matching major; the script never starts a server itself.
    [[ " $SUPPORTED_PG_MAJORS " == *" $base_major "* ]] || { err "Base is PostgreSQL $base_major; supported majors: $SUPPORTED_PG_MAJORS"; return 1; }
    recovery_major="${RECOVERY_PG_MAJOR:-}"
    if [[ -z "$recovery_major" ]] && command -v postgres >/dev/null 2>&1; then
        recovery_major="$(postgres --version 2>/dev/null | sed -nE 's/.*[^0-9]([0-9]+)(\.[0-9]+)?[^0-9]*$/\1/p')"
    fi
    [[ -z "$recovery_major" || "$recovery_major" == "$base_major" ]] || { err "Base is PostgreSQL $base_major but the recovery server is $recovery_major; majors must match"; return 1; }
    [[ "$target" == /* && ! -L "$target" ]] || { err "Use an absolute, non-symlink target"; return 1; }
    [[ -n "$target_time" && "$wal" =~ ^/[A-Za-z0-9_./-]+$ && -d "$wal" ]] || { err "WAL directory and target time are required"; return 1; }
    [[ ! -e "$target" || ( -d "$target" && -z "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ) ]] || { err "Target must be NEW or EMPTY"; return 1; }
    target_time=$(date -u -d "$target_time" '+%Y-%m-%d %H:%M:%S+00')
    [[ ! -d "$base/pg_tblspc" || -z "$(find "$base/pg_tblspc" -mindepth 1 -maxdepth 1 -print -quit)" ]] || { err "External tablespaces need an explicit recovery mapping"; return 1; }
    pg_verifybackup "$base"
    if [[ "$dry" -eq 1 ]]; then
        log "Verified base; would prepare $target for recovery to $target_time. No server started."
        return
    fi
    mkdir -p "$target"
    chmod 700 "$target"
    cp -a "$base/." "$target/"
    rm -f "$target/standby.signal"
    cat >> "$target/postgresql.auto.conf" <<EOF
restore_command = 'cp $wal/%f %p'
recovery_target_time = '$target_time'
recovery_target_action = 'pause'
EOF
    touch "$target/recovery.signal"
    log "Prepared $target. Start an ISOLATED PostgreSQL $base_major instance as its OS owner; verify target reached before promotion."
}

if [[ "${1:-}" == --pitr ]]; then
    shift
    prepare_pitr "$@"
    exit
fi

# ─── تحليل المعاملات ───────────────────────────────────────────
BACKUP_FILE="${1:-}"
TABLE=""
DRY_RUN=0
FORCE=0

if [[ -z "$BACKUP_FILE" ]]; then
    err "الاستخدام: $0 <backup_file> [--table NAME] [--dry-run] [--force]"
    exit 1
fi
shift || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --table)   TABLE="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --force)   FORCE=1; shift ;;
        *) err "معامل غير معروف: $1"; exit 1 ;;
    esac
done

# ─── ١. التحقّق من وجود الملفّ وسلامته ─────────────────────────
if [[ ! -f "$BACKUP_FILE" ]]; then
    err "ملفّ النسخة غير موجود: $BACKUP_FILE"
    exit 1
fi

log "فحص سلامة النسخة: $BACKUP_FILE"
if ! pg_restore --list "$BACKUP_FILE" > /dev/null 2>&1; then
    err "النسخة تالفة أو ليست بصيغة custom (pg_dump -Fc). توقّف."
    exit 1
fi

TABLE_COUNT=$(pg_restore --list "$BACKUP_FILE" | awk '/TABLE DATA/{n++} END {print n+0}')
log "فهرس النسخة قابل للقراءة — $TABLE_COUNT جدولاً؛ هذا لا يثبت الاستعادة"

# ─── ٢. dry-run: اعرض المحتوى دون تنفيذ ────────────────────────
if [[ "$DRY_RUN" -eq 1 ]]; then
    warn "وضع dry-run — لن يُنفَّذ شيء. محتوى النسخة:"
    pg_restore --list "$BACKUP_FILE" | awk '/TABLE DATA/ && n++ < 30'
    exit 0
fi

# ─── ٣. تأكيد قبل الكتابة (إلّا مع --force) ─────────────────────
if [[ "$FORCE" -ne 1 ]]; then
    if [[ -n "$TABLE" ]]; then
        warn "ستُستعاد الجدول '$TABLE' فوق $PGDATABASE@$PGHOST"
    else
        warn "⚠ استعادة كاملة ستكتب فوق كلّ بيانات $PGDATABASE@$PGHOST"
    fi
    read -r -p "متابعة؟ اكتب 'yes' للتأكيد: " confirm
    if [[ "$confirm" != "yes" ]]; then
        log "أُلغيت الاستعادة."
        exit 0
    fi
fi

# ─── ٤. التنفيذ ────────────────────────────────────────────────
RESTORE_ARGS=(
    --host="$PGHOST" --port="$PGPORT" --username="$PGUSER"
    --dbname="$PGDATABASE" --verbose --no-owner --no-privileges --exit-on-error
)

if [[ -n "$TABLE" ]]; then
    log "استعادة انتقائيّة للجدول: $TABLE"
    pg_restore "${RESTORE_ARGS[@]}" --data-only --table="$TABLE" "$BACKUP_FILE"
else
    log "استعادة كاملة (parallel jobs=$PARALLEL_JOBS)"
    pg_restore "${RESTORE_ARGS[@]}" --clean --if-exists \
        --jobs="$PARALLEL_JOBS" "$BACKUP_FILE"
fi

log "✓ اكتملت الاستعادة بنجاح"

# ─── ٥. تحقّق سريع بعد الاستعادة ───────────────────────────────
log "تحقّق: عدد الجداول في القاعدة المستعادة"
psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
     --dbname="$PGDATABASE" -tAc \
     "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" \
     2>/dev/null || warn "تعذّر التحقّق التلقائي (تحقّق يدويّاً)"
