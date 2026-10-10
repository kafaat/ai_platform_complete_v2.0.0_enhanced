#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# probe_schema_state.sh — قراءةٌ فقط: هويّةُ القاعدة وحالةُ المخطَّط مقابل MANIFEST.
#
# MIGRATION-STATE-IN-PRODUCTION-IS-UNREAD-01: المُهاجرُ بلا جدول schema_migrations —
# يُعيد تطبيقَ MANIFEST كلَّه (idempotent)، فحالةُ الهجرات تُستدَلّ من كائنات المخطَّط.
# هذا السكربت يستخرج من ملفّات MANIFEST (بترتيبها) كلَّ `CREATE TABLE IF NOT EXISTS <t>`
# و`ALTER TABLE <t> ADD COLUMN IF NOT EXISTS <c>` ويسأل القاعدة عمّا هو موجود، ثمّ يسمّي
# **أوّلَ ملفٍّ في MANIFEST له كائنٌ غائب** — مؤشّرَ الحالة الجزئيّة (المُشغِّلُ يقف عند
# أوّل خطأ بـON_ERROR_STOP فما قبل أوّل غائبٍ مطبَّقٌ مرجَّحاً، وما بعده لا).
#
# لا يكتب شيئاً: الجلسةُ كلُّها `default_transaction_read_only=on` وتُؤكَّد من الخادم.
# المتغيّرات: PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE (أو PROBE_PGUSER/PROBE_PGPASSWORD
# لدورٍ أدنى صلاحيّةً)، MIG_DIR (افتراضيّ /migrations).
# المخرجُ الآليّ: سطرُ `SCHEMA_STATE …` الأخير؛ الخروج 0 = قُرئت الحالة (غيابُ كائنات ليس
# خطأً هنا بل معلومة)، 3 = تعذّرت القراءة.
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

MIG_DIR="${MIG_DIR:-/migrations}"
PROBE_USER="${PROBE_PGUSER:-$PGUSER}"
PROBE_PASSWORD="${PROBE_PGPASSWORD:-${PGPASSWORD:-}}"
export PGOPTIONS="-c default_transaction_read_only=on ${PGOPTIONS:-}"

probe_sql() {
  PGPASSWORD="$PROBE_PASSWORD" psql -X -v ON_ERROR_STOP=1 -h "$PGHOST" -p "${PGPORT:-5432}" \
    -U "$PROBE_USER" -d "$PGDATABASE" -At -F '|' "$@"
}

manifest_files() { grep -vE '^\s*#|^\s*$' "$MIG_DIR/MANIFEST.txt"; }

# (file, kind, table, column) — بترتيب MANIFEST ثمّ ترتيب الأسطر داخل الملفّ.
expected_objects() {
  local f
  while IFS= read -r f; do
    [ -f "$MIG_DIR/$f" ] || { echo "MANIFEST_FILE_MISSING $f" >&2; return 3; }
    # grep بلا مطابقةٍ يُعيد 1 — وليس خطأً هنا (ملفٌّ بلا جداول/أعمدة جديدة) تحت set -e/pipefail.
    { grep -ioE 'CREATE TABLE IF NOT EXISTS\s+[a-z0-9_]+' "$MIG_DIR/$f" || true; } \
      | awk -v f="$f" '{print f"|table|"tolower($NF)"|"}'
    { grep -ioE 'ALTER TABLE\s+[a-z0-9_]+\s+ADD COLUMN IF NOT EXISTS\s+[a-z0-9_]+' "$MIG_DIR/$f" || true; } \
      | awk -v f="$f" '{print f"|column|"tolower($3)"|"tolower($NF)}'
  done < <(manifest_files)
}

echo "─ قراءةُ هويّة القاعدة (read-only) ${PGHOST}:${PGPORT:-5432}/${PGDATABASE} كـ${PROBE_USER} ─"
identity="$(probe_sql -c "SELECT current_setting('transaction_read_only'), version(), current_database(), current_user, inet_server_addr(), (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)")" || {
  echo "SCHEMA_STATE readable=false reason=connect_or_query_failed host=${PGHOST}:${PGPORT:-5432}" >&2
  exit 3
}
IFS='|' read -r ro version database user addr super <<<"$identity"
if [ "$ro" != "on" ]; then
  echo "SCHEMA_STATE readable=false reason=session_not_read_only" >&2
  exit 3
fi
echo "  transaction_read_only=${ro} · ${version%%,*} · db=${database} · user=${user} (super=${super}) · server=${addr:-local}"

expected="$(expected_objects)"
n_tables=$(printf '%s\n' "$expected" | grep -c '|table|' || true)
n_columns=$(printf '%s\n' "$expected" | grep -c '|column|' || true)
echo "─ المتوقَّع من MANIFEST ($(manifest_files | wc -l) ملفّاً): ${n_tables} جدولاً · ${n_columns} عموداً ─"

# قائمةُ القيم تُرسَل إلى الخادم مرّةً واحدة؛ المعرّفاتُ من [a-z0-9_] فقط بالبناء أعلاه.
values="$(printf '%s\n' "$expected" | awk -F'|' 'NF>=4 {printf "(%d,'"'"'%s'"'"','"'"'%s'"'"','"'"'%s'"'"','"'"'%s'"'"'),", NR, $1, $2, $3, $4}')"
values="${values%,}"
missing="$(probe_sql -c "
WITH expected(ord, file, kind, tbl, col) AS (VALUES ${values})
SELECT ord, file, kind, tbl, col FROM expected e
WHERE (kind = 'table'  AND to_regclass('public.' || tbl) IS NULL)
   OR (kind = 'column' AND NOT EXISTS (
         SELECT 1 FROM information_schema.columns c
         WHERE c.table_schema = 'public' AND c.table_name = e.tbl AND c.column_name = e.col))
ORDER BY ord")" || { echo "SCHEMA_STATE readable=false reason=presence_query_failed" >&2; exit 3; }

m_tables=$(printf '%s\n' "$missing" | grep -c '|table|' || true)
m_columns=$(printf '%s\n' "$missing" | grep -c '|column|' || true)
first_missing="$(printf '%s\n' "$missing" | head -1 | cut -d'|' -f2)"
if [ -n "$missing" ]; then
  echo "─ كائناتٌ غائبة (${m_tables} جدولاً · ${m_columns} عموداً) — أوّلُها في ترتيب MANIFEST: ${first_missing} ─"
  printf '%s\n' "$missing" | head -20 | awk -F'|' '{printf "  ✗ %s: %s %s%s\n", $2, $3, $4, ($5==""?"":"."$5)}'
  [ "$(printf '%s\n' "$missing" | wc -l)" -gt 20 ] && echo "  … (الباقي محذوف من العرض لا من العدّ)"
else
  echo "  ✓ كلُّ الجداول والأعمدة المتوقَّعة موجودة."
fi
echo "SCHEMA_STATE readable=true read_only=on db=${database} user=${user} tables=$((n_tables - m_tables))/${n_tables} columns=$((n_columns - m_columns))/${n_columns} first_missing=${first_missing:-none}"
