#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# unfreeze_local_rehearsal.sh — تجربة فكّ التجميد على PostgreSQL **محلّيّة فقط**.
#
# يُعيد محلّيّاً الشرطين ٣ و٤ من MIGRATION_UNFREEZE_RUNBOOK_20261028.md §٤.١ (تجربة الترقية على
# بيانات + حقن الفشل في v235) ويضيف v237 (مسودّة GATE-01) فوقها، ثمّ يقارن مسار الترقية بمسار
# البناء من الصفر. لا يلمس Railway ولا أيّ قاعدة غير محلّيّة: يرفض أيَّ PGHOST غير loopback.
#
# المتغيّرات: PGHOST (loopback فقط) · PGPORT · PGUSER (superuser محلّيّ) · PGPASSWORD
#             APP_ROLE_PASSWORD (افتراضيّ app_test_password) · OUT (مجلّد الأدلّة)
# الخروج: 0 = كلّ الفحوص PASS · 1 = فحصٌ واحد على الأقلّ FAIL · 2 = رفضُ الإعداد
# ══════════════════════════════════════════════════════════════════
set -uo pipefail

case "${PGHOST:-}" in
  localhost|127.0.0.1|::1) ;;
  *) echo "REFUSED: PGHOST='${PGHOST:-}' ليس loopback — هذا السكربت محلّيّ فقط" >&2; exit 2;;
esac
: "${PGPORT:?PGPORT required}" "${PGUSER:?PGUSER required}" "${PGPASSWORD:?PGPASSWORD required}"
if [ "${SAHOOL_MIGRATE_APPLY:-}" = "1" ]; then
  echo "REFUSED: SAHOOL_MIGRATE_APPLY=1 مضبوط في هذه الصدفة — أزله؛ التجربة لا تحتاجه" >&2; exit 2
fi
export PGHOST PGPORT PGUSER PGPASSWORD
APP_PW="${APP_ROLE_PASSWORD:-app_test_password}"
ROOT="$(git rev-parse --show-toplevel)"; cd "$ROOT"
OUT="${OUT:-$ROOT/.local-rehearsal/$(date -u +%Y%m%dT%H%M%SZ)}"; mkdir -p "$OUT"
UP=rehearsal_upgrade; FRESH=rehearsal_fresh; REF=rehearsal_v235_ref
RESULTS="$OUT/RESULTS.tsv"; : > "$RESULTS"
fails=0

q()  { psql -X -q -v ON_ERROR_STOP=1 -d "$1" "${@:2}"; }
qa() { psql -X -At -v ON_ERROR_STOP=1 -d "$1" -c "$2"; }
rec() {  # rec <id> <PASS|FAIL|INFO> <detail>
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" | tee -a "$RESULTS"
  [ "$2" = FAIL ] && fails=$((fails + 1)); return 0
}
dropdb_if() { psql -X -q -d postgres -c "DROP DATABASE IF EXISTS \"$1\"" >/dev/null; }
mkdb() { dropdb_if "$1"; psql -X -q -d postgres -c "CREATE DATABASE \"$1\" ${2:+TEMPLATE \"$2\"}" >/dev/null; }
apply_one() {  # apply_one <db> <file> <log>
  PGOPTIONS='-c lock_timeout=5s -c statement_timeout=15min -c search_path=public' \
    psql -X -v ON_ERROR_STOP=1 -d "$1" -f "$2" >"$3" 2>&1 </dev/null
}

# ── R0 هويّة ما يُقاس ───────────────────────────────────────────────
{
  echo "head=$(git rev-parse HEAD)"; echo "branch=$(git rev-parse --abbrev-ref HEAD)"
  echo "server=$(qa postgres 'SHOW server_version')"
  echo "postgis=$(qa postgres "SELECT default_version FROM pg_available_extensions WHERE name='postgis'")"
  sha256sum migrations/v234_*.sql migrations/v235_*.sql migrations/v236_*.sql migrations/v237_*.sql migrations/MANIFEST.txt
} > "$OUT/R0_identity.txt"
rec R0 INFO "$(head -3 "$OUT/R0_identity.txt" | tr '\n' ' ')"
v=$(qa postgres 'SHOW server_version_num'); [ "$v" -ge 160000 ] && [ "$v" -lt 170000 ] \
  && rec R0.pg16 PASS "server_version_num=$v" || rec R0.pg16 FAIL "need PG16, got $v"

# ── R1 خطّ أساس شبيه بالحيّ: MANIFEST حتى ما قبل v234 ثمّ v206 أخيراً ─────────
grep -vE '^[[:space:]]*(#|$)' migrations/MANIFEST.txt | awk '/^v234_/{exit} {print}' > "$OUT/MANIFEST.live_like.txt"
grep -qx 'v206_rls_final_hardening.sql' "$OUT/MANIFEST.live_like.txt" || true
echo v206_rls_final_hardening.sql >> "$OUT/MANIFEST.live_like.txt"
mkdb "$UP"
if bash scripts/ci/apply_migration_manifest.sh --host "$PGHOST" --port "$PGPORT" --user "$PGUSER" --db "$UP" \
     --manifest "$OUT/MANIFEST.live_like.txt" >"$OUT/R1_baseline_apply.log" 2>&1; then
  rec R1.baseline PASS "$(tail -1 "$OUT/R1_baseline_apply.log")"
else rec R1.baseline FAIL "see R1_baseline_apply.log"; echo "baseline failed — stopping"; exit 1; fi

# ── R2 بيانات تاريخيّة قبل الترقية (ما لا تملكه قاعدة CI الفارغة) ─────────────
T=aaaaaaaa-2350-4000-8000-00000000000a
if q "$UP" >"$OUT/R2_seed.log" 2>&1 <<SQL
INSERT INTO dispatch_decisions(decision_id,tenant_id,recommendation_id,action_type,state,risk_level)
  SELECT 'hist-dispatch-'||g, '$T'::uuid,'rec','inspection','blocked','low' FROM generate_series(1,500) g;
INSERT INTO decision_record(decision_id,tenant_id,decision_type,decision_value)
  SELECT 'hist-decision-'||g, '$T'::uuid,'inspection','{}' FROM generate_series(1,500) g;
INSERT INTO execution_ledger(ledger_id,tenant_id,decision_id,action_type,outcome,content_hash)
  SELECT 'hist-ledger-'||g, '$T'::uuid,'hist-dispatch-'||g,'inspection','executed','unchanged' FROM generate_series(1,500) g;
INSERT INTO online_learning_updates(tenant_id,update_id,model_id,feature_set_id,action)
  SELECT '$T'::uuid,'hist-olu-'||g,'m','fs','observe' FROM generate_series(1,200) g;
INSERT INTO soil_sampling_plans(plan_id,tenant_id,field_id,mode,payload)
  VALUES ('hist-empty-tenant','', 'f1','grid','{}');
SQL
then rec R2.seed PASS "500×3 decision-chain rows, 200 learning rows, 1 empty-tenant row"
else rec R2.seed FAIL "see R2_seed.log"; fi
data_fp() { qa "$1" "SELECT md5(string_agg(x, '|' ORDER BY x)) FROM (
  SELECT 'd|'||decision_id||'|'||tenant_id FROM decision_record UNION ALL
  SELECT 'p|'||decision_id||'|'||tenant_id FROM dispatch_decisions UNION ALL
  SELECT 'l|'||ledger_id||'|'||decision_id FROM execution_ledger UNION ALL
  SELECT 'o|'||update_id FROM online_learning_updates) s(x)"; }
PRE_DATA=$(data_fp "$UP"); rec R2.data_fp INFO "$PRE_DATA"

# ── R3 v234 ملفّاً واحداً + فحوص §٤.٣ ─────────────────────────────────
if apply_one "$UP" migrations/v234_learning_agronomic_review.sql "$OUT/R3_v234.log"; then
  c=$(qa "$UP" "SELECT count(*) FROM pg_constraint WHERE conrelid='online_learning_updates'::regclass AND conname LIKE 'chk_oluj_agronomic_%' AND convalidated")
  u=$(qa "$UP" "SELECT count(*) FROM online_learning_updates WHERE NOT (review_status='unreviewed' AND agronomically_approved=false)")
  [ "$c" = 2 ] && [ "$u" = 0 ] && rec R3.v234 PASS "2 validated constraints; 0 historical rows changed review state" \
    || rec R3.v234 FAIL "constraints=$c rows_not_unreviewed=$u"
else rec R3.v234 FAIL "see R3_v234.log"; fi

# ── R4 حقن الفشل في v235 (§٤.١-٤): لكلّ k: نسخة ← أوّل k عبارات ← الملفّ كاملاً ← مطابقة التعريف ─
python3 -I - migrations/v235_decision_chain_correlation.sql "$OUT/v235_stmts" <<'PY'
import os, sys
src, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
stmts, cur, in_dollar = [], [], False
for line in open(src, encoding="utf-8"):
    cur.append(line)
    if line.count("$$") % 2:
        in_dollar = not in_dollar
    if not in_dollar and line.rstrip().endswith(";"):
        stmts.append("".join(cur)); cur = []
if "".join(cur).strip():
    stmts.append("".join(cur))
for i, s in enumerate(stmts, 1):
    open(os.path.join(outdir, f"{i:03d}.sql"), "w", encoding="utf-8").write(s)
print(len(stmts))
PY
N=$(ls "$OUT/v235_stmts" | wc -l)
defs_fp() { qa "$1" "SELECT string_agg(x, E'\n' ORDER BY x) FROM (
  SELECT 'idx|'||indexrelid::regclass||'|'||indisvalid||'|'||pg_get_indexdef(indexrelid) FROM pg_index
   WHERE indexrelid::regclass::text LIKE 'idx_%_correlation' UNION ALL
  SELECT 'fn|'||proname||'|'||md5(pg_get_functiondef(oid)) FROM pg_proc
   WHERE proname IN ('sahool_chain_correlation_root','sahool_chain_correlation_immutable','sahool_platform_chain_correlation') UNION ALL
  SELECT 'tg|'||tgrelid::regclass||'|'||tgname||'|'||tgenabled::text||'|'||pg_get_triggerdef(oid) FROM pg_trigger
   WHERE tgname LIKE 'trg_%_correlation_%' AND NOT tgisinternal UNION ALL
  SELECT 'col|'||table_name||'|'||data_type||'|'||coalesce(col_description(format('public.%I',table_name)::regclass, ordinal_position::int),'')
    FROM information_schema.columns WHERE table_schema='public' AND column_name='correlation_id'
     AND table_name IN ('decision_record','dispatch_decisions','execution_ledger','as_applied_irrigation_runs','as_applied_irrigation_receipts')
  ) s(x)"; }
mkdb "$REF" "$UP"
apply_one "$REF" migrations/v235_decision_chain_correlation.sql "$OUT/R4_ref.log" || rec R4.ref FAIL "reference apply failed"
defs_fp "$REF" > "$OUT/R4_ref_defs.txt" || rec R4.ref_query FAIL "fingerprint query failed"
REF_DATA=$(data_fp "$REF")
ri=$(grep -c '^idx|' "$OUT/R4_ref_defs.txt"); rf=$(grep -c '^fn|' "$OUT/R4_ref_defs.txt"); rt=$(grep -c '^tg|' "$OUT/R4_ref_defs.txt")
[ "$ri" = 5 ] && [ "$rf" = 3 ] && [ "$rt" = 10 ] && rec R4.ref PASS "indexes=5 functions=3 triggers=10 (all from one clean apply)" \
  || rec R4.ref FAIL "indexes=$ri functions=$rf triggers=$rt"
inj_fail=0
for k in $(seq 1 $((N - 1))); do
  db="rehearsal_v235_k$k"; mkdb "$db" "$UP"
  cat $(ls "$OUT"/v235_stmts/*.sql | head -n "$k") > "$OUT/v235_partial_k$k.sql"
  if ! apply_one "$db" "$OUT/v235_partial_k$k.sql" "$OUT/R4_k${k}_partial.log"; then
    rec "R4.k$k" FAIL "partial prefix did not apply"; inj_fail=1; dropdb_if "$db"; continue; fi
  if ! apply_one "$db" migrations/v235_decision_chain_correlation.sql "$OUT/R4_k${k}_rerun.log"; then
    rec "R4.k$k" FAIL "re-run after partial failed"; inj_fail=1; dropdb_if "$db"; continue; fi
  if ! cur=$(defs_fp "$db"); then rec "R4.k$k" FAIL "fingerprint query failed"; inj_fail=1
  elif [ "$cur" != "$(cat "$OUT/R4_ref_defs.txt")" ] || [ "$(data_fp "$db")" != "$REF_DATA" ]; then
    diff <(printf '%s\n' "$cur") "$OUT/R4_ref_defs.txt" > "$OUT/R4_k${k}_diff.txt"; rec "R4.k$k" FAIL "definitions/data differ"; inj_fail=1; fi
  dropdb_if "$db"; rm -f "$OUT/v235_partial_k$k.sql"
done
[ "$ri" = 5 ] && [ "$inj_fail" = 0 ] && rec R4.fault_injection PASS "stopped after each of $((N - 1))/$N statements; re-run restored identical definitions and data"
[ "$PRE_DATA" = "$REF_DATA" ] && rec R4.data_unchanged PASS "historical rows identical after v235" || rec R4.data_unchanged FAIL "data fingerprint changed"
# تكذيب الكاشف: فهرسٌ بالاسم نفسه وتعريفٍ آخر — IF NOT EXISTS يتخطّاه، فيجب أن تكشفه المقارنة
mkdb rehearsal_v235_falsify "$UP"
qa rehearsal_v235_falsify "ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS correlation_id uuid;
  CREATE INDEX idx_decision_record_correlation ON decision_record (correlation_id)" >/dev/null
apply_one rehearsal_v235_falsify migrations/v235_decision_chain_correlation.sql "$OUT/R4_falsify.log"
if [ "$(defs_fp rehearsal_v235_falsify)" != "$(cat "$OUT/R4_ref_defs.txt")" ]; then
  rec R4.detector_falsified PASS "a same-name index with another definition is caught (IF NOT EXISTS would hide it)"
else rec R4.detector_falsified FAIL "the comparison did not see a planted definition drift"; fi
dropdb_if rehearsal_v235_falsify
dropdb_if "$REF"

# ── R5 v235 على قاعدة الترقية تحت كاتبٍ متزامن (قياس انتظار الأقفال) ────────────
python3 -I - "$UP" "$OUT/R5_writer.txt" <<'PY' &
import os, sys, time, subprocess
db, out = sys.argv[1], sys.argv[2]
worst, n, errs, t_end = 0.0, 0, 0, time.time() + 8
while time.time() < t_end:
    t0 = time.time()
    r = subprocess.run(["psql", "-X", "-q", "-d", db, "-c",
        f"INSERT INTO decision_record(decision_id,tenant_id,decision_type,decision_value) "
        f"VALUES ('live-w-{n}-{int(t0*1e6)}','aaaaaaaa-2350-4000-8000-00000000000a','inspection','{{}}')"],
        capture_output=True, text=True)
    worst = max(worst, time.time() - t0); n += 1; errs += r.returncode != 0
open(out, "w").write(f"writes={n} errors={errs} worst_latency_ms={worst*1000:.0f}\n")
PY
WPID=$!; sleep 1
( time apply_one "$UP" migrations/v235_decision_chain_correlation.sql "$OUT/R5_v235.log" ) 2>"$OUT/R5_v235_time.txt"; r5=$?
wait "$WPID"
if [ "$r5" = 0 ]; then
  [ -s "$OUT/R4_ref_defs.txt" ] && [ "$(defs_fp "$UP")" = "$(cat "$OUT/R4_ref_defs.txt")" ] && rec R5.v235 PASS "$(cat "$OUT/R5_writer.txt") apply_$(grep real "$OUT/R5_v235_time.txt" | tr '\t' ' ')" \
    || rec R5.v235 FAIL "definitions differ from reference"
else rec R5.v235 FAIL "see R5_v235.log"; fi
# قبول وظيفيّ: كتابةٌ مشروعة تنجح وتعديل الهويّة يُرفض
cid=$(qa "$UP" "INSERT INTO decision_record(decision_id,tenant_id,decision_type,decision_value) VALUES ('acc-1','$T','inspection','{}') RETURNING correlation_id")
[ -n "$cid" ] && rec R5.accept_insert PASS "server-owned correlation_id=$cid" || rec R5.accept_insert FAIL "no correlation_id"
if qa "$UP" "UPDATE decision_record SET tenant_id='bbbbbbbb-2350-4000-8000-00000000000b' WHERE decision_id='acc-1'" >/dev/null 2>"$OUT/R5_reject.txt"; then
  rec R5.reject_tenant_change FAIL "tenant_id change was accepted"
else rec R5.reject_tenant_change PASS "$(head -1 "$OUT/R5_reject.txt")"; fi
qa "$UP" "UPDATE decision_record SET decision_value='{\"ok\":1}' WHERE decision_id='acc-1'" >/dev/null 2>&1 \
  && rec R5.accept_update PASS "ordinary update still accepted" || rec R5.accept_update FAIL "ordinary update rejected"

# ── R6 v236 ─────────────────────────────────────────────────────────
if apply_one "$UP" migrations/v236_raster_follow_up_requests.sql "$OUT/R6_v236.log"; then
  f=$(qa "$UP" "SELECT relrowsecurity::text||':'||relforcerowsecurity::text FROM pg_class WHERE oid='raster_follow_up_requests'::regclass")
  [ "$f" = "true:true" ] && rec R6.v236 PASS "RLS+FORCE on raster_follow_up_requests" || rec R6.v236 FAIL "rls:force=$f"
else rec R6.v236 FAIL "see R6_v236.log"; fi

# ── R7 v237 (مسودّة GATE-01) + v206 أخيراً كما في MANIFEST ─────────────────────
if apply_one "$UP" migrations/v237_tenant_isolation_hardening.sql "$OUT/R7_v237.log" \
   && apply_one "$UP" migrations/v206_rls_final_hardening.sql "$OUT/R7_v206.log"; then
  w=$(grep -c "T9: .*soil_sampling_plans" "$OUT/R7_v237.log" || true)
  rec R7.v237 PASS "applied; T9 warned on seeded empty-tenant row: $w line(s)"
else rec R7.v237 FAIL "see R7_v237.log / R7_v206.log"; fi
TEST_DATABASE_URL="postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$UP" \
  python3 scripts/migrations/report_not_valid_constraint_violations.py > "$OUT/R7_not_valid_report.txt" 2>&1; rr=$?
grep -q "FAIL  \[v237_tenant_isolation_hardening.sql\] soil_sampling_plans" "$OUT/R7_not_valid_report.txt" && [ "$rr" = 1 ] \
  && rec R7.not_valid_report PASS "report names the seeded '' row (exit 1 = expected: clean before VALIDATE)" \
  || rec R7.not_valid_report FAIL "exit=$rr; see R7_not_valid_report.txt"

# ── R8 إعادة MANIFEST الفرع كاملاً على قاعدة الترقية (idempotency) ─────────────
bash scripts/ci/apply_migration_manifest.sh --host "$PGHOST" --port "$PGPORT" --user "$PGUSER" --db "$UP" \
  >"$OUT/R8_reapply.log" 2>&1 && rec R8.reapply PASS "$(tail -1 "$OUT/R8_reapply.log")" || rec R8.reapply FAIL "see R8_reapply.log"

# ── R9 فحص المخطّط قراءةً فقط ───────────────────────────────────────────
PGDATABASE="$UP" MIG_DIR="$ROOT/migrations" bash migrations/probe_schema_state.sh > "$OUT/R9_probe.txt" 2>&1
grep -q 'SCHEMA_INSPECTION status=PASS.*first_missing=none' "$OUT/R9_probe.txt" \
  && rec R9.probe PASS "$(grep -o 'SCHEMA_INSPECTION status=[A-Z]* read_only=[a-z]*' "$OUT/R9_probe.txt")" \
  || rec R9.probe FAIL "$(grep SCHEMA_INSPECTION "$OUT/R9_probe.txt" | tail -1)"

# ── R10 الترقية == البناء من الصفر (مخطّطاً) ───────────────────────────────
mkdb "$FRESH"
bash scripts/ci/apply_migration_manifest.sh --host "$PGHOST" --port "$PGPORT" --user "$PGUSER" --db "$FRESH" \
  >"$OUT/R10_fresh.log" 2>&1 || rec R10.fresh FAIL "fresh build failed"
norm() { pg_dump -s -x -O -d "$1" | grep -vE '^(--|SET |SELECT pg_catalog.set_config|\\(un)?restrict )' | sed '/^$/d' | LC_ALL=C sort; }
norm "$FRESH" > "$OUT/R10_fresh_once.schema"
# المُهاجر يُعيد MANIFEST كاملاً في كلّ تشغيل، وCI يطبّقه مرّتين — فالمرجع «من الصفر مرّتين».
bash scripts/ci/apply_migration_manifest.sh --host "$PGHOST" --port "$PGPORT" --user "$PGUSER" --db "$FRESH" \
  >"$OUT/R10_fresh_second.log" 2>&1 || rec R10.fresh_second FAIL "second fresh pass failed"
norm "$UP" > "$OUT/R10_upgrade.schema"; norm "$FRESH" > "$OUT/R10_fresh.schema"
d12=$(diff "$OUT/R10_fresh_once.schema" "$OUT/R10_fresh.schema" | grep -c '^[<>]' || true)
rec R10.fresh_once_vs_twice INFO "$d12 schema lines differ between one and two passes on an empty DB (pre-existing path-dependence, not v234–v237)"
if diff -q "$OUT/R10_upgrade.schema" "$OUT/R10_fresh.schema" >/dev/null; then
  rec R10.upgrade_equals_fresh PASS "$(wc -l < "$OUT/R10_fresh.schema") normalized schema lines identical"
else diff "$OUT/R10_upgrade.schema" "$OUT/R10_fresh.schema" > "$OUT/R10_schema.diff"
  rec R10.upgrade_equals_fresh FAIL "$(grep -c '^[<>]' "$OUT/R10_schema.diff") differing lines — see R10_schema.diff"; fi

# ── R11 الدور المقيَّد على القاعدتين (كما وظيفة Integration في ci.yml) ───────────
for db in "$UP" "$FRESH"; do
q "$db" >>"$OUT/R11_role.log" 2>&1 <<SQL
DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_app_test') THEN
  CREATE ROLE sahool_app_test LOGIN PASSWORD '$APP_PW' NOSUPERUSER NOBYPASSRLS NOINHERIT; END IF; END \$\$;
GRANT CONNECT ON DATABASE "$db" TO sahool_app_test;
GRANT USAGE ON SCHEMA public TO sahool_app_test;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sahool_app_test;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sahool_app_test;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO sahool_app_test;
SQL
done
flags=$(qa postgres "SELECT rolsuper::text||':'||rolbypassrls::text FROM pg_roles WHERE rolname='sahool_app_test'")
[ "$flags" = "false:false" ] && rec R11.role PASS "sahool_app_test super:bypassrls=$flags" || rec R11.role FAIL "flags=$flags"

# ── R12 اختبارات v237 الحيّة على قاعدة **الترقية** (لا الفارغة فقط) ─────────────
TEST_DATABASE_ADMIN_URL="postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$UP" \
TEST_DATABASE_URL="postgresql://sahool_app_test:$APP_PW@$PGHOST:$PGPORT/$UP" \
  python3 -m pytest tests_v9/test_v237_tenant_isolation_live_pg.py -q -p no:cacheprovider -o addopts= \
  --junitxml="$OUT/R12_v237_upgrade.xml" > "$OUT/R12_v237_upgrade.txt" 2>&1 \
  && rec R12.v237_live_on_upgrade PASS "$(tail -1 "$OUT/R12_v237_upgrade.txt")" \
  || rec R12.v237_live_on_upgrade FAIL "$(tail -1 "$OUT/R12_v237_upgrade.txt")"

echo "fails=$fails" >> "$RESULTS"
echo; echo "══ RESULTS: $RESULTS  (fails=$fails) ══"
[ "$fails" = 0 ]
