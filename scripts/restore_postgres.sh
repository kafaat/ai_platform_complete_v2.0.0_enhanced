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

# ─── ألوان للمخرجات ────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[restore]${NC} $*"; }
warn() { echo -e "${YELLOW}[restore]${NC} $*"; }
err()  { echo -e "${RED}[restore]${NC} $*" >&2; }

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

TABLE_COUNT=$(pg_restore --list "$BACKUP_FILE" | grep -c "TABLE DATA" || echo 0)
log "النسخة سليمة — تحوي $TABLE_COUNT جدولاً"

# ─── ٢. dry-run: اعرض المحتوى دون تنفيذ ────────────────────────
if [[ "$DRY_RUN" -eq 1 ]]; then
    warn "وضع dry-run — لن يُنفَّذ شيء. محتوى النسخة:"
    pg_restore --list "$BACKUP_FILE" | grep "TABLE DATA" | head -30
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
    --dbname="$PGDATABASE" --verbose --no-owner --no-privileges
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
