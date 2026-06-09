#!/usr/bin/env bash
# اختبار إنفاذ عزل المستأجرين (RLS) فعليًّا — لا مجرّد تفعيله.
# يطبّق الترحيلات على قاعدة جديدة، يتحقّق أنّ كل جدول RLS يُفرض (FORCE)، ثم
# يثبت العزل عبر دور **غير ممتاز** (كما ينبغي في الإنتاج): مستأجر A لا يرى
# بيانات B، والعكس، وبلا سياق مستأجر لا يُرى شيء.
#
# الاستخدام: PGHOST=/tmp/pgrun PGUSER=sahool_user bash tests_v9/test_rls_enforcement.sh
set -uo pipefail
PGHOST="${PGHOST:-/tmp/pgrun}"
OWNER="${PGUSER:-sahool_user}"
PSQL_OWNER="psql -h $PGHOST -U $OWNER -tA -v ON_ERROR_STOP=1"
MIG="$(cd "$(dirname "$0")/../migrations" && pwd)"
PASS=0; FAIL=0
ck(){ if [ "$2" = "$3" ]; then echo "  ✓ $1"; PASS=$((PASS+1)); else echo "  ✗ $1 (توقّع '$3' فحصل '$2')"; FAIL=$((FAIL+1)); fi; }

echo "── إعداد: قاعدة نظيفة + كل الترحيلات ──"
psql -h "$PGHOST" -U "$OWNER" -d postgres -q -c "DROP DATABASE IF EXISTS rlstest;" >/dev/null 2>&1
/usr/lib/postgresql/16/bin/createdb -h "$PGHOST" -U "$OWNER" rlstest
applied=0
while read -r f; do
  [ -z "$f" ] && continue; case "$f" in \#*) continue;; esac
  psql -h "$PGHOST" -U "$OWNER" -d rlstest -q -v ON_ERROR_STOP=1 -f "$MIG/$f" >/dev/null 2>&1 && applied=$((applied+1)) || echo "    ✗ migration $f"
done < <(grep -vE '^\s*#|^\s*$' "$MIG/MANIFEST.txt")
echo "  طُبِّق $applied ترحيلًا"
PSQL="psql -h $PGHOST -U $OWNER -d rlstest -tA -v ON_ERROR_STOP=1"

echo "── ١) كل جداول RLS تُفرض الآن (FORCE) ──"
NOTFORCED=$($PSQL -c "SELECT count(*) FROM pg_class WHERE relkind='r' AND relnamespace='public'::regnamespace AND relrowsecurity AND NOT relforcerowsecurity;")
RLS_TOTAL=$($PSQL -c "SELECT count(*) FROM pg_class WHERE relkind='r' AND relnamespace='public'::regnamespace AND relrowsecurity;")
ck "صفر جدول RLS بلا FORCE (كان 19)" "$NOTFORCED" "0"
echo "    (إجمالي جداول RLS مفروضة: $RLS_TOTAL)"

echo "── ٢) دور تطبيق غير ممتاز (محاكاة الإنتاج) ──"
$PSQL -c "DROP ROLE IF EXISTS sahool_app;" >/dev/null 2>&1 || true
$PSQL -c "CREATE ROLE sahool_app LOGIN NOSUPERUSER NOBYPASSRLS;" >/dev/null
$PSQL -c "GRANT USAGE ON SCHEMA public TO sahool_app;
          GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sahool_app;
          GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sahool_app;" >/dev/null
SUPER=$($PSQL -c "SELECT (rolsuper OR rolbypassrls) FROM pg_roles WHERE rolname='sahool_app';")
ck "دور التطبيق ليس superuser ولا bypassrls" "$SUPER" "f"

echo "── ٣) إدخال بيانات اختبار لمستأجرين A و B (كمالك superuser) ──"
A="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"; B="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
$PSQL -c "INSERT INTO field_boundaries(field_id,field_name,tenant_id) VALUES
  ('fA','حقل-A','$A'),('fB','حقل-B','$B');" >/dev/null
# نعدّ صفوف الاختبار فقط (نعزل عن بيانات seed في init_v8)
ck "صفّا الاختبار موجودان" "$($PSQL -c "SELECT count(*) FROM field_boundaries WHERE field_name IN ('حقل-A','حقل-B');")" "2"

echo "── ٤) العزل عبر دور التطبيق غير الممتاز (الخاصّية الأمنيّة الجوهريّة) ──"
APP="psql -h $PGHOST -U sahool_app -d rlstest -tA"
A_OWN=$($APP -c "SELECT set_config('app.current_tenant','$A',false); SELECT count(*) FROM field_boundaries WHERE field_name='حقل-A';" | tail -1)
A_SEES_B=$($APP -c "SELECT set_config('app.current_tenant','$A',false); SELECT count(*) FROM field_boundaries WHERE field_name='حقل-B';" | tail -1)
ck "مستأجر A يرى صفّه (حقل-A)" "$A_OWN" "1"
ck "مستأجر A لا يرى صفّ B (عزل!)" "$A_SEES_B" "0"
B_OWN=$($APP -c "SELECT set_config('app.current_tenant','$B',false); SELECT count(*) FROM field_boundaries WHERE field_name='حقل-B';" | tail -1)
B_SEES_A=$($APP -c "SELECT set_config('app.current_tenant','$B',false); SELECT count(*) FROM field_boundaries WHERE field_name='حقل-A';" | tail -1)
ck "مستأجر B يرى صفّه (حقل-B)" "$B_OWN" "1"
ck "مستأجر B لا يرى صفّ A (عزل!)" "$B_SEES_A" "0"

echo "── ٥) بلا سياق مستأجر ⇒ لا يُرى أيّ صفّ اختبار ──"
SEEN_NONE=$($APP -c "SELECT set_config('app.current_tenant','',false); SELECT count(*) FROM field_boundaries WHERE field_name IN ('حقل-A','حقل-B');" | tail -1)
ck "بلا app.current_tenant ⇒ 0 من صفوف الاختبار" "$SEEN_NONE" "0"

echo "── ٦) WITH CHECK: A لا يكتب صفّاً بـtenant مغاير لسياقه ──"
# مع FORCE + سياسة، WITH CHECK يرفض إدخال صفّ بـtenant_id ≠ السياق الحالي
$APP -c "SELECT set_config('app.current_tenant','$A',false);
         INSERT INTO field_boundaries(field_id,field_name,tenant_id) VALUES ('fX','تسلل','$B');" >/dev/null 2>&1
RC=$?
ck "INSERT بـtenant مغاير (B) مرفوض في سياق A (WITH CHECK)" "$([ $RC -ne 0 ] && echo blocked || echo allowed)" "blocked"
LEAK=$($PSQL -c "SELECT count(*) FROM field_boundaries WHERE field_name='تسلل';")
ck "لم يُكتب أيّ صفّ تسلّل (تحقّق كمالك)" "$LEAK" "0"

echo "────────────────────────────────────────────"
echo "  RLS ENFORCEMENT: $PASS نجاح | $FAIL فشل"
echo "────────────────────────────────────────────"
[ "$FAIL" -eq 0 ] || exit 1
