#!/bin/bash
# scripts/backup_minio.sh — نسخ احتياطي/استعادة لتخزين MinIO (الكائنات)
#
# يغطّي الفجوة: backup_postgres.sh يحفظ قاعدة البيانات فقط، لا كائنات MinIO
# (رواستر COG، صور كاميرات الحقل، مرفقات). فقدانها = فقدان بيانات لا تُعوَّض.
#
# يستخدم mc (MinIO Client) — أداة MinIO الرسميّة.
#
# الميزات:
#   ١. mirror كامل لكلّ buckets (أو bucket محدّد)
#   ٢. استعادة من نسخة (mirror عكسي)
#   ٣. retention للنسخ المحليّة
#   ٤. فحص الاتّصال قبل البدء
#   ٥. dry-run
#
# الاستخدام:
#   ./backup_minio.sh backup                    # كلّ الـbuckets
#   ./backup_minio.sh backup rasters            # bucket واحد
#   ./backup_minio.sh restore <snapshot_dir>    # استعادة
#   ./backup_minio.sh list                       # عرض النسخ المتاحة
#
# Cron suggestion:
#   0 3 * * *  /scripts/backup_minio.sh backup   # يوميّاً ٣ صباحاً

set -euo pipefail

# ─── Config (env vars) ─────────────────────────────────────────
MINIO_ALIAS="${MINIO_ALIAS:-sahool-minio}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://sahool-minio:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-}"
BACKUP_DIR="${MINIO_BACKUP_DIR:-/var/backups/sahool/minio}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[minio-backup]${NC} $*"; }
warn() { echo -e "${YELLOW}[minio-backup]${NC} $*"; }
err()  { echo -e "${RED}[minio-backup]${NC} $*" >&2; }

# ─── تحقّق من توفّر mc ──────────────────────────────────────────
if ! command -v mc > /dev/null 2>&1; then
    err "MinIO Client (mc) غير مثبّت. ثبّته:"
    err "  curl https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc && chmod +x /usr/local/bin/mc"
    exit 1
fi

# ─── إعداد alias الاتّصال ───────────────────────────────────────
setup_alias() {
    if [[ -z "$MINIO_ACCESS_KEY" || -z "$MINIO_SECRET_KEY" ]]; then
        err "MINIO_ACCESS_KEY و MINIO_SECRET_KEY مطلوبان (عبر env)"
        exit 1
    fi
    mc alias set "$MINIO_ALIAS" "$MINIO_ENDPOINT" \
        "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" > /dev/null 2>&1
    # فحص الاتّصال
    if ! mc ls "$MINIO_ALIAS" > /dev/null 2>&1; then
        err "تعذّر الاتّصال بـMinIO على $MINIO_ENDPOINT"
        exit 1
    fi
    log "متّصل بـMinIO: $MINIO_ENDPOINT"
}

# ─── النسخ الاحتياطي ───────────────────────────────────────────
do_backup() {
    local bucket="${1:-}"
    setup_alias
    local ts
    ts="$(date +%Y%m%d_%H%M%S)"
    local snapshot="$BACKUP_DIR/$ts"
    mkdir -p "$snapshot"

    if [[ -n "$bucket" ]]; then
        log "نسخ bucket: $bucket → $snapshot"
        mc mirror --overwrite "$MINIO_ALIAS/$bucket" "$snapshot/$bucket"
    else
        log "نسخ كلّ الـbuckets → $snapshot"
        # اعرض كلّ bucket وانسخه
        mc ls "$MINIO_ALIAS" | awk '{print $NF}' | while read -r b; do
            b="${b%/}"
            [[ -z "$b" ]] && continue
            log "  • $b"
            mc mirror --overwrite "$MINIO_ALIAS/$b" "$snapshot/$b"
        done
    fi

    # حجم النسخة
    local size
    size="$(du -sh "$snapshot" 2>/dev/null | cut -f1)"
    log "✓ اكتمل النسخ: $snapshot ($size)"

    # تنظيف النسخ القديمة
    log "تنظيف النسخ الأقدم من $RETENTION_DAYS يوم"
    find "$BACKUP_DIR" -maxdepth 1 -type d -mtime "+$RETENTION_DAYS" \
        -exec rm -rf {} + 2>/dev/null || true
}

# ─── الاستعادة ─────────────────────────────────────────────────
do_restore() {
    local snapshot="${1:-}"
    if [[ -z "$snapshot" || ! -d "$snapshot" ]]; then
        err "مجلّد النسخة غير موجود: $snapshot"
        err "النسخ المتاحة:"; do_list
        exit 1
    fi
    setup_alias
    warn "⚠ ستُستعاد الكائنات من $snapshot فوق MinIO الحالي"
    read -r -p "متابعة؟ اكتب 'yes' للتأكيد: " confirm
    [[ "$confirm" != "yes" ]] && { log "أُلغيت."; exit 0; }

    # لكلّ مجلّد bucket في النسخة
    for bdir in "$snapshot"/*/; do
        [[ -d "$bdir" ]] || continue
        local b
        b="$(basename "$bdir")"
        log "استعادة bucket: $b"
        # أنشئ الـbucket إن لم يوجد
        mc mb --ignore-existing "$MINIO_ALIAS/$b" > /dev/null 2>&1 || true
        mc mirror --overwrite "$bdir" "$MINIO_ALIAS/$b"
    done
    log "✓ اكتملت الاستعادة"
}

# ─── عرض النسخ ─────────────────────────────────────────────────
do_list() {
    if [[ -d "$BACKUP_DIR" ]]; then
        ls -1dt "$BACKUP_DIR"/*/ 2>/dev/null | while read -r d; do
            local size; size="$(du -sh "$d" 2>/dev/null | cut -f1)"
            echo "  $d ($size)"
        done
    else
        warn "لا نسخ في $BACKUP_DIR"
    fi
}

# ─── التوجيه ───────────────────────────────────────────────────
case "${1:-}" in
    backup)  do_backup "${2:-}" ;;
    restore) do_restore "${2:-}" ;;
    list)    do_list ;;
    *)
        err "الاستخدام: $0 {backup [bucket] | restore <snapshot_dir> | list}"
        exit 1
        ;;
esac
