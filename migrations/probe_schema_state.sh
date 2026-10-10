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
#
# **العقد (مراجعةُ المالك 2026-10-10):** السطرُ الآليّ الأخير
#   SCHEMA_INSPECTION status=PASS|INCOMPLETE|ERROR read_only=true manifest_sha256=… files_parsed=…
#     expected_tables=… present_tables=… expected_columns=… present_columns=… first_missing=<file|none>
# PASS = اكتملت قراءةُ **كلّ** ملفّات MANIFEST وكلُّ المتوقَّع موجود؛ INCOMPLETE = اكتملت القراءة
# وبعضُ المتوقَّع غائب؛ ERROR = تعذّر الاتّصالُ أو التحليل (ملفٌّ غيرُ مقروء، MANIFEST فارغ، عدٌّ
# لا يطابق) ⇒ **لا** يُصدَر `readable=true` ولا PASS جزئيّ، والخروج 3. PASS يعني اكتمالَ نطاق
# الفحص المُعلَن فقط (الجداولُ والأعمدة) لا اعتمادَ القاعدة للإنتاج.
# `SCHEMA_STATE …` يُطبَع أيضاً للتوافق مع القرّاء الأقدم.
#
# المتغيّرات: PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE (أو PROBE_PGUSER/PROBE_PGPASSWORD
# لدورٍ أدنى صلاحيّةً)، MIG_DIR (افتراضيّ /migrations).
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

MIG_DIR="${MIG_DIR:-/migrations}"
PROBE_USER="${PROBE_PGUSER:-$PGUSER}"
PROBE_PASSWORD="${PROBE_PGPASSWORD:-${PGPASSWORD:-}}"
export PGOPTIONS="-c default_transaction_read_only=on ${PGOPTIONS:-}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# read_only يبقى unknown حتّى يؤكّده الخادم (مراجعةُ المالك الرابعة 2026-10-10): خطأٌ قبل الاتّصال لا
# يدّعي جلسةً لم تُنشأ؛ وجلسةٌ أنكرت read-only تُعلَن false.
READ_ONLY=unknown
fail() { # $1 = reason, $2.. = extra key=value
  echo "SCHEMA_INSPECTION status=ERROR read_only=${READ_ONLY} reason=$1 ${*:2}" >&2
  echo "SCHEMA_STATE readable=false reason=$1" >&2
  exit 3
}

probe_sql() {
  PGPASSWORD="$PROBE_PASSWORD" psql -X -v ON_ERROR_STOP=1 -h "$PGHOST" -p "${PGPORT:-5432}" \
    -U "$PROBE_USER" -d "$PGDATABASE" -At -F '|' "$@"
}

# ── ١) MANIFEST: قائمةٌ في ملفٍّ (لا process substitution — فشلُ المُنتِج لا ينتقل إلى الحلقة) ──
[ -r "$MIG_DIR/MANIFEST.txt" ] || fail manifest_unreadable "path=$MIG_DIR/MANIFEST.txt"
grep -vE '^\s*#|^\s*$' "$MIG_DIR/MANIFEST.txt" > "$WORK/files" || true
n_files=$(wc -l < "$WORK/files" | tr -d ' ')
[ "$n_files" -gt 0 ] || fail manifest_empty
manifest_sha256="$(sha256sum "$MIG_DIR/MANIFEST.txt" 2>/dev/null | cut -d' ' -f1 || echo unavailable)"

# ── ٢) المتوقَّع (file|kind|table|column) بترتيب MANIFEST ثمّ ترتيب الأسطر؛ كلُّ ملفٍّ يُعَدّ عند قراءته ──
: > "$WORK/expected"
parsed=0
while IFS= read -r f; do
  [ -r "$MIG_DIR/$f" ] || fail manifest_file_unreadable "file=$f files_parsed=$parsed"
  # grep بلا مطابقةٍ يُعيد 1 — ليس خطأً (ملفٌّ بلا جداول/أعمدة جديدة)؛ غيرُ ذلك (≥2) خطأُ قراءة.
  # الأسطرُ تُسطَّح أوّلاً: ٥٢ عبارةَ ADD COLUMN في MANIFEST تمتدّ على سطرين (ALTER TABLE x ⏎ ADD COLUMN …)
  # وكان grep السطريّ يُسقطها (127 بدل 179) — القياسُ يطابق الآن الجردَ المرجعيّ.
  tr '\n' ' ' < "$MIG_DIR/$f" > "$WORK/flat" || fail parse_failed "file=$f"
  grep -ioE 'CREATE TABLE IF NOT EXISTS\s+[a-z0-9_]+' "$WORK/flat" > "$WORK/t" || [ $? -eq 1 ] || fail parse_failed "file=$f"
  grep -ioE 'ALTER TABLE\s+[a-z0-9_]+\s+ADD COLUMN IF NOT EXISTS\s+[a-z0-9_]+' "$WORK/flat" > "$WORK/c" || [ $? -eq 1 ] || fail parse_failed "file=$f"
  awk -v f="$f" '{print f"|table|"tolower($NF)"|"}' "$WORK/t" >> "$WORK/expected"
  awk -v f="$f" '{print f"|column|"tolower($3)"|"tolower($NF)}' "$WORK/c" >> "$WORK/expected"
  parsed=$((parsed + 1))
done < "$WORK/files"
[ "$parsed" -eq "$n_files" ] || fail manifest_incompletely_parsed "files_parsed=$parsed files=$n_files"

n_tables=$(grep -c '|table|' "$WORK/expected" || true)
n_columns=$(grep -c '|column|' "$WORK/expected" || true)

# ── ٢ب) عقدُ الحدّ الأدنى (مراجعةُ المالك الرابعة): ملفٌّ بجوار MANIFEST يربط بصمتَه بأقلّ عددٍ معتمدٍ من
# الكائنات المستخرَجة؛ فلا يُصدَر PASS على تحليلٍ أخرج صفراً (ملفّاتٌ لا تطابق الأنماط) ولا على MANIFEST
# غيرِ الذي كُتب له العقد. الإنتاجُ: schema_probe_contract.env المُولَّد من MANIFEST الحاليّ ويحرسه اختبار.
CONTRACT="$MIG_DIR/schema_probe_contract.env"
[ -r "$CONTRACT" ] || fail contract_missing "path=$CONTRACT"
c_sha="$(grep -oE '^MANIFEST_SHA256=[0-9a-f]{64}$' "$CONTRACT" | cut -d= -f2 || true)"
c_tables="$(grep -oE '^MIN_TABLES=[0-9]+$' "$CONTRACT" | cut -d= -f2 || true)"
c_columns="$(grep -oE '^MIN_COLUMNS=[0-9]+$' "$CONTRACT" | cut -d= -f2 || true)"
[ -n "$c_sha" ] && [ -n "$c_tables" ] && [ -n "$c_columns" ] || fail contract_malformed "path=$CONTRACT"
[ "$c_sha" = "$manifest_sha256" ] || fail manifest_contract_mismatch "contract_sha256=${c_sha:0:12} manifest_sha256=${manifest_sha256:0:12}"
[ $((n_tables + n_columns)) -gt 0 ] || fail no_objects_extracted "files_parsed=$parsed"
[ "$n_tables" -ge "$c_tables" ] && [ "$n_columns" -ge "$c_columns" ] \
  || fail objects_below_contract "extracted_tables=$n_tables min_tables=$c_tables extracted_columns=$n_columns min_columns=$c_columns"

# ── ٣) الهويّة، والجلسةُ read-only مؤكَّدةٌ من الخادم ──
echo "─ قراءةُ هويّة القاعدة (read-only) ${PGHOST}:${PGPORT:-5432}/${PGDATABASE} كـ${PROBE_USER} ─"
identity="$(probe_sql -c "SELECT current_setting('transaction_read_only'), version(), current_database(), current_user, inet_server_addr(), (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)")" \
  || fail connect_or_query_failed "host=${PGHOST}:${PGPORT:-5432}"
IFS='|' read -r ro version database user addr super <<<"$identity"
[ "$ro" = "on" ] || { READ_ONLY=false; fail session_not_read_only; }
READ_ONLY=true
echo "  transaction_read_only=${ro} · ${version%%,*} · db=${database} · user=${user} (super=${super}) · server=${addr:-local}"
echo "─ المتوقَّع من MANIFEST (${n_files} ملفّاً، كلُّها قُرئت؛ sha256=${manifest_sha256:0:12}…): ${n_tables} جدولاً · ${n_columns} عموداً ─"

# ── ٤) الغائب: استعلامٌ واحد؛ المعرّفاتُ من [a-z0-9_] فقط بالبناء أعلاه ──
values="$(awk -F'|' 'NF>=4 {printf "(%d,'"'"'%s'"'"','"'"'%s'"'"','"'"'%s'"'"','"'"'%s'"'"'),", NR, $1, $2, $3, $4}' "$WORK/expected")"
values="${values%,}"
missing=""
if [ -n "$values" ]; then
  missing="$(probe_sql -c "
WITH expected(ord, file, kind, tbl, col) AS (VALUES ${values})
SELECT ord, file, kind, tbl, col FROM expected e
WHERE (kind = 'table'  AND to_regclass('public.' || tbl) IS NULL)
   OR (kind = 'column' AND NOT EXISTS (
         SELECT 1 FROM information_schema.columns c
         WHERE c.table_schema = 'public' AND c.table_name = e.tbl AND c.column_name = e.col))
ORDER BY ord")" || fail presence_query_failed
fi

m_tables=$(printf '%s\n' "$missing" | grep -c '|table|' || true)
m_columns=$(printf '%s\n' "$missing" | grep -c '|column|' || true)
first_missing="$(printf '%s\n' "$missing" | head -1 | cut -d'|' -f2)"
if [ -n "$missing" ]; then
  echo "─ كائناتٌ غائبة (${m_tables} جدولاً · ${m_columns} عموداً) — أوّلُها في ترتيب MANIFEST: ${first_missing} ─"
  printf '%s\n' "$missing" | head -20 | awk -F'|' '{printf "  ✗ %s: %s %s%s\n", $2, $3, $4, ($5==""?"":"."$5)}'
  [ "$(printf '%s\n' "$missing" | wc -l)" -gt 20 ] && echo "  … (الباقي محذوف من العرض لا من العدّ)"
  status=INCOMPLETE
else
  echo "  ✓ كلُّ الجداول والأعمدة المتوقَّعة موجودة."
  status=PASS
fi
# حدُّ الدلالة (مراجعةُ المالك 2026-10-10): وجودُ الجداول والأعمدة لا يُثبت تطبيقَ الهجرات كاملةً —
# القيودُ والفهارسُ وسياساتُ RLS والدوالّ لا تُقارَن هنا. PASS ليس اعتماداً للقاعدة.
echo "  ملاحظة: القياسُ وجودُ الجداول/الأعمدة فقط — القيودُ والفهارسُ وRLS والدوالّ خارج هذه القراءة."
echo "SCHEMA_STATE readable=true read_only=on db=${database} user=${user} tables=$((n_tables - m_tables))/${n_tables} columns=$((n_columns - m_columns))/${n_columns} first_missing=${first_missing:-none} scope=tables_and_columns_only"
echo "SCHEMA_INSPECTION status=${status} read_only=${READ_ONLY} manifest_sha256=${manifest_sha256} files_parsed=${parsed} expected_tables=${n_tables} present_tables=$((n_tables - m_tables)) expected_columns=${n_columns} present_columns=$((n_columns - m_columns)) first_missing=${first_missing:-none}"
