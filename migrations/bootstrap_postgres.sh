#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# bootstrap_postgres.sh — تشغيل PostgreSQL + PostGIS وتطبيق كل الـmigrations
#
# يعمل على أيّ جهاز فيه Docker. أمر واحد:
#   ./bootstrap_postgres.sh
#
# ما يفعله:
#   ١. يشغّل حاوية postgis/postgis:15-3.4 (PostGIS جاهز)
#   ٢. ينتظر جاهزيّة القاعدة (pg_isready)
#   ٣. يطبّق الـmigrations بالترتيب الصحيح (من MANIFEST.txt — لا أبجدي)
#   ٤. يتحقّق: extensions + عدد الجداول + جداول مفتاحيّة
#
# متغيّرات (اختياريّة):
#   PGPASSWORD (افتراضي: sahool_dev_pw)، PGPORT (5432)، PGDATABASE (sahool)
#
# ── نموذج الدورين (مهمّ لأمان RLS) ────────────────────────────────
#   مالك الهجرات (PGUSER، الافتراضي sahool_user) دور مُمتاز (superuser في صورة
#   postgres الرسميّة) — يُنشئ الجداول/الامتدادات/السياسات. لكنّ superuser
#   **يتجاوز RLS حتى مع FORCE**، فلو اتّصل التطبيق به لانهار عزل المستأجرين.
#   لذلك نُنشئ بعد الهجرات دوراً مقيّداً للتشغيل: sahool_app
#   (NOSUPERUSER NOBYPASSRLS LOGIN) بصلاحيّات DML + EXECUTE + USAGE فقط.
#   على المُشغّل توجيه DATABASE_URL للتطبيق نحو sahool_app (لا sahool_user)
#   ليبقى RLS فعّالاً وقت التشغيل.
#   APP_DB_PASSWORD (افتراضي: sahool_app_pw) كلمة سرّ دور التطبيق المقيّد.
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-sahool-postgres-dev}"
PG_IMAGE="postgis/postgis:15-3.4"
PG_PASSWORD="${PGPASSWORD:-sahool_dev_pw}"
PG_PORT="${PGPORT:-5432}"
PG_DB="${PGDATABASE:-sahool}"
PG_USER="${PGUSER:-sahool_user}"
APP_ROLE="${APP_DB_ROLE:-sahool_app}"
APP_PASSWORD="${APP_DB_PASSWORD:-sahool_app_pw}"
MIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "═══ SAHOOL PostgreSQL Bootstrap ═══"

# تحقّق من Docker
if ! command -v docker >/dev/null 2>&1; then
  echo "✗ Docker غير مثبّت. ثبّته أوّلاً: https://docs.docker.com/get-docker/"
  exit 1
fi

# ١. شغّل الحاوية (احذف القديمة لو موجودة)
echo "─ ١. تشغيل حاوية PostGIS ($PG_IMAGE) ─"
docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$PG_CONTAINER" \
  -e POSTGRES_PASSWORD="$PG_PASSWORD" \
  -e POSTGRES_USER="$PG_USER" \
  -e POSTGRES_DB="$PG_DB" \
  -p "127.0.0.1:${PG_PORT}:5432" \
  "$PG_IMAGE" >/dev/null
echo "  ✓ الحاوية: $PG_CONTAINER (منفذ 127.0.0.1:$PG_PORT)"

# ٢. انتظر الجاهزيّة
echo "─ ٢. انتظار جاهزيّة القاعدة ─"
for i in $(seq 1 30); do
  if docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
    echo "  ✓ جاهزة (بعد ${i}s)"
    break
  fi
  sleep 1
  [ "$i" -eq 30 ] && { echo "✗ المهلة انتهت"; exit 1; }
done

# ٣. طبّق الـmigrations بالترتيب الصحيح من MANIFEST
echo "─ ٣. تطبيق الـmigrations (ترتيب MANIFEST، لا أبجدي) ─"
psql_exec() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" "$@"; }
while IFS= read -r line; do
  line="$(echo "$line" | sed 's/#.*//' | xargs)"   # احذف التعليقات والمسافات
  [ -z "$line" ] && continue
  f="$MIG_DIR/$line"
  if [ ! -f "$f" ]; then echo "  ⚠ مفقود: $line (تخطّي)"; continue; fi
  printf "  → %-38s " "$line"
  if psql_exec < "$f" >/dev/null 2>/tmp/mig_err; then
    echo "✓"
  else
    echo "✗"; echo "    الخطأ:"; sed 's/^/      /' /tmp/mig_err | head -5; exit 1
  fi
done < "$MIG_DIR/MANIFEST.txt"

# ٤. التحقّق
echo "─ ٤. التحقّق ─"
echo -n "  extensions: "
psql_exec -tAc "SELECT string_agg(extname,', ') FROM pg_extension WHERE extname IN ('postgis','uuid-ossp','pgcrypto');"
echo -n "  عدد الجداول: "
psql_exec -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
echo "  جداول مفتاحيّة موجودة؟"
for t in fields commands events field_lifecycle sharing_keys; do
  exists=$(psql_exec -tAc "SELECT to_regclass('public.$t') IS NOT NULL;")
  [ "$exists" = "t" ] && echo "    ✓ $t" || echo "    ✗ $t مفقود"
done

# ٥. دور التطبيق المقيّد (least-privilege) لتفعيل عزل RLS وقت التشغيل
# ──────────────────────────────────────────────────────────────────
# يُنشأ **بعد** كلّ الهجرات (الجداول/الدوال/التسلسلات موجودة). الدور:
#   NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE LOGIN
# فلا يتجاوز RLS أبداً (عكس مالك الهجرات المُمتاز). يُمنح DML + EXECUTE + USAGE
# فقط — وهو كافٍ لأنّ التطبيق لا ينفّذ DDL وقت التشغيل (DML + SET LOCAL +
# استدعاء emit_event()). ALTER DEFAULT PRIVILEGES يغطّي كائنات الهجرات المستقبليّة.
# آمن لإعادة التشغيل (idempotent): إنشاء الدور محروس، والمنح غير ضارّ بالتكرار.
echo "─ ٥. إنشاء دور التطبيق المقيّد ($APP_ROLE — NOBYPASSRLS) ─"
# ملاحظة: استبدال متغيّرات psql بصيغة colon-quote لا يحدث داخل سلاسل dollar-quoted
# ($$...$$)، لذلك يُنشأ الدور عبر CREATE ROLE مشروط بـ\gexec (خارج أيّ DO)،
# ثمّ تُثبَّت السمات وكلمة السرّ بـALTER ROLE (آمن للتكرار).
psql_exec -v app_role="$APP_ROLE" -v app_pw="$APP_PASSWORD" <<'SQL'
-- ١) أنشئ الدور فقط إن لم يكن موجوداً (يُولّد SQL ثمّ يُنفّذ بـ\gexec)
SELECT format('CREATE ROLE %I LOGIN', :'app_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec

-- ٢) ثبّت السمات الأمنيّة وكلمة السرّ (idempotent سواء أُنشئ الآن أو سابقاً)
-- NOINHERIT: يمنع توريث صلاحيّات أيّ دور عضو فيه — عقد الدور المقيَّد (IRR-F01 Gate A).
-- آمن هنا: الدور يُمنَح DML/EXECUTE/USAGE مباشرةً (لا عبر عضويّة)، فلا يُكسَر أيّ grant.
ALTER ROLE :"app_role"
  LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'app_pw';

-- صلاحيّات وقت التشغيل: DML + EXECUTE + USAGE فقط (لا DDL)
GRANT USAGE ON SCHEMA public TO :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO :"app_role";

-- صلاحيّات افتراضيّة لكائنات الهجرات المستقبليّة (تُمنح للمالك الذي يُنشئ الكائنات)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO :"app_role";

-- A7 (مرجع مشترك admin_boundaries): قراءة-عامّة/كتابة-محمِّل. sahool_app **SELECT فقط** —
-- تُنزَع الكتابة (طبقة مرجعيّة تتغيّر بلا provenance = انجراف صامت؛ الكتابة عبر المُحمِّل الإداريّ الموثّق).
-- (الهجرات قبل bootstrap فالجدولان موجودان؛ :'app_role' مربوط في هذه الكتلة.)
DO $$
BEGIN
  IF to_regclass('public.admin_boundaries') IS NOT NULL THEN
    EXECUTE 'REVOKE INSERT, UPDATE, DELETE ON admin_boundaries FROM ' || quote_ident(:'app_role');
  END IF;
  IF to_regclass('public.admin_boundaries_source') IS NOT NULL THEN
    EXECUTE 'REVOKE INSERT, UPDATE, DELETE ON admin_boundaries_source FROM ' || quote_ident(:'app_role');
  END IF;
  -- SEASON-RECORD-01 (v201): سجلّ موسم append-only — **لا DELETE أبداً** (التصحيح = إصدار مُبطِل).
  -- يبقى SELECT/INSERT/UPDATE (قبول untrusted→accepted) — تُنزَع DELETE فقط (برهان سلبيّ).
  IF to_regclass('public.season_records')    IS NOT NULL THEN EXECUTE 'REVOKE DELETE ON season_records FROM '    || quote_ident(:'app_role'); END IF;
  IF to_regclass('public.season_crop')       IS NOT NULL THEN EXECUTE 'REVOKE DELETE ON season_crop FROM '       || quote_ident(:'app_role'); END IF;
  IF to_regclass('public.season_events')     IS NOT NULL THEN EXECUTE 'REVOKE DELETE ON season_events FROM '     || quote_ident(:'app_role'); END IF;
  IF to_regclass('public.season_harvest')    IS NOT NULL THEN EXECUTE 'REVOKE DELETE ON season_harvest FROM '    || quote_ident(:'app_role'); END IF;
  IF to_regclass('public.season_cost_items') IS NOT NULL THEN EXECUTE 'REVOKE DELETE ON season_cost_items FROM ' || quote_ident(:'app_role'); END IF;
END $$;
SQL
echo "  ✓ الدور $APP_ROLE جاهز (NOSUPERUSER NOBYPASSRLS) + admin_boundaries SELECT-only (A7) + season_records لا-DELETE (v201)"

# ─ ٥.١ دور التحكّم لدالّة resolve_ingest_source (SCOUT-INGEST-01 B1.2b) ─
# NOSUPERUSER + BYPASSRLS + SELECT على external_ingest_sources فقط، يملك الدالّة (SECURITY DEFINER).
# FORCE RLS يسري على مالك الجدول ⇒ مالك غير BYPASS يُجوّع resolver (كلّ توكن 403). أقلّ سطح تصعيد:
# دور لا يتّصل، لا superuser، بلا DML، SELECT على جدول واحد. راجع docs/specs/...B1.2b §1.1.
echo "─ ٥.١ دور التحكّم sahool_ingest_resolver (NOSUPERUSER BYPASSRLS، مالك الدالّة فقط) ─"
psql_exec <<'SQL'
SELECT format('CREATE ROLE %I NOLOGIN', 'sahool_ingest_resolver')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_ingest_resolver')
\gexec

ALTER ROLE sahool_ingest_resolver NOLOGIN NOSUPERUSER NOINHERIT BYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT USAGE ON SCHEMA public TO sahool_ingest_resolver;

DO $$
BEGIN
  IF to_regclass('public.external_ingest_sources') IS NOT NULL THEN
    GRANT SELECT ON external_ingest_sources TO sahool_ingest_resolver;   -- الحدّ الأدنى (SELECT ليس DML)
  END IF;
  IF to_regprocedure('public.resolve_ingest_source(text)') IS NOT NULL THEN
    -- المالك يتجاوز FORCE (BYPASSRLS) فتعمل الدالّة قبل ضبط app.current_tenant
    EXECUTE 'ALTER FUNCTION resolve_ingest_source(TEXT) OWNER TO sahool_ingest_resolver';
  END IF;
  -- B1.3: دالّتا الإسقاط (claim/complete) SECURITY DEFINER يملكهما resolver (BYPASSRLS) فتمسحان
  -- عابراً للمستأجرين وتحدّثان projection_status دون منح UPDATE لـsahool_ingest. تحتاجان SELECT+UPDATE
  -- على external_submissions (تحديث بكرة المعالجة فقط؛ trigger الخامّ يمنع مسّ الدليل).
  IF to_regclass('public.external_submissions') IS NOT NULL THEN
    GRANT SELECT, UPDATE ON external_submissions TO sahool_ingest_resolver;
  END IF;
  IF to_regprocedure('public.claim_submissions_for_projection(integer,integer)') IS NOT NULL THEN
    EXECUTE 'ALTER FUNCTION claim_submissions_for_projection(INT, INT) OWNER TO sahool_ingest_resolver';
  END IF;
  IF to_regprocedure('public.complete_submission_projection(bigint,text,text)') IS NOT NULL THEN
    EXECUTE 'ALTER FUNCTION complete_submission_projection(BIGINT, TEXT, TEXT) OWNER TO sahool_ingest_resolver';
  END IF;
END $$;
SQL
# EXECUTE لـ$APP_ROLE مُغطّى بـ"GRANT EXECUTE ON ALL FUNCTIONS ... TO app_role" في الخطوة ٥ (تسبق هنا،
# والدالّة موجودة إذ تُطبَّق الهجرات قبل bootstrap) — يُبطِل REVOKE FROM PUBLIC (v198) دون 500.
echo "  ✓ sahool_ingest_resolver جاهز (يملك resolve_ingest_source؛ EXECUTE لـ$APP_ROLE عبر الخطوة ٥)"

# ─ ٥.٢ دور خدمة الإدخال sahool_ingest (SCOUT-INGEST-01 B1.2b — scout-ingest-service) ─
# أقلّ منح: SELECT+INSERT على external_submissions + EXECUTE على resolve_ingest_source.
# NOBYPASSRLS (RLS فعّال؛ الخدمة تضبط app.current_tenant) · **لا UPDATE/DELETE** (تحديث الحالة لكاتب B1.3).
echo "─ ٥.٢ دور خدمة الإدخال sahool_ingest (NOBYPASSRLS، SELECT+INSERT فقط) ─"
psql_exec -v ing_pw="${INGEST_DB_PASSWORD:-sahool_ingest_pw}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', 'sahool_ingest')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_ingest')
\gexec

ALTER ROLE sahool_ingest LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'ing_pw';
GRANT USAGE ON SCHEMA public TO sahool_ingest;

DO $$
BEGIN
  IF to_regclass('public.external_submissions') IS NOT NULL THEN
    GRANT SELECT, INSERT ON external_submissions TO sahool_ingest;   -- لا UPDATE/DELETE
    GRANT USAGE, SELECT ON SEQUENCE external_submissions_id_seq TO sahool_ingest;
  END IF;
  IF to_regprocedure('public.resolve_ingest_source(text)') IS NOT NULL THEN
    GRANT EXECUTE ON FUNCTION resolve_ingest_source(TEXT) TO sahool_ingest;
  END IF;
  -- B1.3: العامل يُدرِج نموذج القراءة المملوك، ونقطة القراءة تختاره؛ التحديث عبر دالّتَي DEFINER فقط.
  IF to_regclass('public.external_field_observations') IS NOT NULL THEN
    GRANT SELECT, INSERT ON external_field_observations TO sahool_ingest;   -- لا UPDATE/DELETE
  END IF;
  IF to_regprocedure('public.claim_submissions_for_projection(integer,integer)') IS NOT NULL THEN
    GRANT EXECUTE ON FUNCTION claim_submissions_for_projection(INT, INT) TO sahool_ingest;
  END IF;
  IF to_regprocedure('public.complete_submission_projection(bigint,text,text)') IS NOT NULL THEN
    GRANT EXECUTE ON FUNCTION complete_submission_projection(BIGINT, TEXT, TEXT) TO sahool_ingest;
  END IF;
  -- SEASON-RECORD-ENTRY-01 §2: scout-ingest is the single writer of the season tables (v201/v202).
  -- SELECT+INSERT+UPDATE — INSERT (draft), UPDATE (draft edits + untrusted→accepted transition);
  -- **لا DELETE** (append-only، التصحيح = إصدار مُبطِل). RLS يبقى فعّالاً (NOBYPASSRLS)، وtriggers
  -- التجميد (v201) تمنع تحوير الأبناء بعد القبول بصرف النظر عن المنح.
  IF to_regclass('public.season_records') IS NOT NULL THEN
    GRANT SELECT, INSERT, UPDATE ON
      season_records, season_crop, season_events, season_harvest, season_cost_items
      TO sahool_ingest;
  END IF;
  -- SEASON-ENTRY-EVENTS-UI: نقطة detail تقرأ الأهليّة من الـVIEW المُشتقّ (security_invoker ⇒ RLS
  -- تبقى بصلاحيّات القارئ) — يحتاج منح SELECT على الـVIEW نفسه (غيابه ⇒ 503 على detail).
  IF to_regclass('public.season_calibration_eligibility') IS NOT NULL THEN
    GRANT SELECT ON season_calibration_eligibility TO sahool_ingest;
  END IF;
END $$;
SQL
echo "  ✓ sahool_ingest جاهز (SELECT+INSERT على submissions+observations؛ SELECT+INSERT+UPDATE على مواسم v201؛ لا DELETE)"

echo ""
echo "═══ تمّ ✓ ═══"
# نموذج الدورين: الهجرات بالمالك المُمتاز، التطبيق بالدور المقيّد ليبقى RLS فعّالاً.
echo "للهجرات/الإدارة:  DATABASE_URL=postgresql://$PG_USER:$PG_PASSWORD@127.0.0.1:$PG_PORT/$PG_DB"
echo "للتطبيق (RLS فعّال): DATABASE_URL=postgresql://$APP_ROLE:$APP_PASSWORD@127.0.0.1:$PG_PORT/$PG_DB"
echo "⚠ لا توجّه التطبيق لـ$PG_USER (مُمتاز/superuser ⇒ يتجاوز RLS ويُبطل عزل المستأجرين)."
echo "للإيقاف:  docker rm -f $PG_CONTAINER"
