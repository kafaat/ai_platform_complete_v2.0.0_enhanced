#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# apply_in_compose.sh — يُطبّق الهجرات على postgres المكدّس من داخل خدمة
# `sahool-migrate` (لمرّة واحدة)، ثمّ يُنشئ دور التطبيق المقيّد sahool_app.
#
# يختلف عن bootstrap_postgres.sh: هذا يتّصل بحاوية postgres قائمة (المكدّس) عبر
# الشبكة (PGHOST=sahool-postgres) لا يُنشئ حاويته. يجعل `docker compose up` ذاتيّ
# التهيئة: قبله كان الإقلاع يفشل (auth يُدرج في users غير الموجود ⇒ ينهار).
#
# متغيّرات (تُمرَّر من compose): PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE،
#   APP_DB_ROLE (افتراضي sahool_app)، APP_DB_PASSWORD.
#
# نموذج الدورين (أمان RLS): مالك الهجرات (PGUSER=sahool_user) مُمتاز يُنشئ
# الكائنات؛ لكنّ superuser يتجاوز RLS حتى مع FORCE — لذا نُنشئ دور تشغيل مقيّداً
# (sahool_app: NOSUPERUSER NOBYPASSRLS) ويجب توجيه DATABASE_URL للتطبيق إليه.
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

MIG_DIR="${MIG_DIR:-/migrations}"
APP_ROLE="${APP_DB_ROLE:-sahool_app}"
APP_PASSWORD="${APP_DB_PASSWORD:-sahool_app_pw}"
APP_ALLOW_SCHEMA_CREATE="${APP_ALLOW_SCHEMA_CREATE:-false}"
# دور المهامّ الخلفيّة (المرسِل/المجدوِل): BYPASSRLS مقصود — يقرأ عابراً للمستأجرين
# (event_outbox/الطقس). يُستعمَل فقط من مسارات الوظائف عبر JOBS_DATABASE_URL، لا التطبيق.
JOBS_ROLE="${JOBS_DB_ROLE:-sahool_jobs}"
JOBS_PASSWORD="${JOBS_DB_PASSWORD:-sahool_jobs_pw}"

# انتظار جاهزيّة القاعدة (depends_on: service_healthy يكفي عادةً — تأمين إضافيّ)
for i in $(seq 1 30); do
  pg_isready -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" >/dev/null 2>&1 && break
  echo "بانتظار postgres ($i)…"; sleep 2
done

psql_exec() { psql -v ON_ERROR_STOP=1 -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" -d "$PGDATABASE" "$@"; }

# حارس وقت التشغيل (حزمة 72 ساعة): v206_rls_final_hardening.sql يجب أن يبقى
# آخر مدخل .sql في MANIFEST دائمًا (يُحصّن كلّ ما قبله؛ أيّ هجرة لاحقة تتجاوزه
# تعيد فتح ثغرات RLS التي يغلقها). الحارس الساكن في CI وحده لا يكفي — هذا
# الفحص يمنع التطبيق بترتيب مكسور حتى لو فات CI.
LAST_SQL="$(grep -E '\.sql[[:space:]]*$' "$MIG_DIR/MANIFEST.txt" | grep -vE '^[[:space:]]*#' | tail -1 | xargs)"
if [ "$LAST_SQL" != "v206_rls_final_hardening.sql" ]; then
  echo "✗ MANIFEST مكسور الترتيب: آخر مدخل .sql هو '${LAST_SQL}' وليس v206_rls_final_hardening.sql" >&2
  exit 1
fi

echo "─ تطبيق الهجرات (ترتيب MANIFEST، لا أبجدي) على ${PGHOST}/${PGDATABASE} ─"
applied=0
while IFS= read -r f; do
  case "$f" in '' | \#*) continue ;; esac
  echo "  → $f"
  psql_exec -f "$MIG_DIR/$f" >/dev/null
  applied=$((applied + 1))
done < <(grep -vE '^\s*#|^\s*$' "$MIG_DIR/MANIFEST.txt")
echo "  ✓ طُبّقت $applied هجرة (idempotent — آمنة على التكرار)"

echo "─ إنشاء دور التطبيق المقيّد (${APP_ROLE} — NOSUPERUSER NOBYPASSRLS NOINHERIT) ─"
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

-- صلاحيّات وقت التشغيل: DML + EXECUTE + USAGE فقط. CREATE يُسحب صراحةً؛
-- أي خدمة ما زالت تُنشئ schema عند الإقلاع يجب نقلها إلى migration job مستقل.
GRANT USAGE ON SCHEMA public TO :"app_role";
REVOKE CREATE ON SCHEMA public FROM :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO :"app_role";

-- صلاحيّات افتراضيّة لكائنات الهجرات المستقبليّة
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO :"app_role";

-- A7 (مرجع مشترك admin_boundaries): sahool_app **SELECT فقط** — تُنزَع الكتابة (الكتابة عبر المُحمِّل الموثّق).
-- حاسم: :'app_role' متغيّر psql يُستبدَل **فقط خارج** كتل dollar-quoted (DO $$…$$).
-- لذا نتجنّب DO ونولّد أوامر REVOKE بـformat() ثمّ ننفّذها بـ\gexec:
--   • :'app_role' خارج أيّ اقتباس دولاريّ ⇒ يعالجه psql · %I يقتبس المعرّف بأمان
--   • WHERE to_regclass(...) IS NOT NULL يحفظ idempotency · \gexec ينفّذ المُولَّد فقط.
SELECT format('REVOKE INSERT, UPDATE, DELETE ON TABLE public.admin_boundaries FROM %I', :'app_role')
WHERE to_regclass('public.admin_boundaries') IS NOT NULL
\gexec
SELECT format('REVOKE INSERT, UPDATE, DELETE ON TABLE public.admin_boundaries_source FROM %I', :'app_role')
WHERE to_regclass('public.admin_boundaries_source') IS NOT NULL
\gexec
-- SEASON-RECORD-01 (v201): سجلّ موسم append-only — **لا DELETE أبداً**. SELECT/INSERT/UPDATE يبقى؛ DELETE يُنزَع.
SELECT format('REVOKE DELETE ON TABLE public.%I FROM %I', t.table_name, :'app_role')
FROM (VALUES
        ('season_records'), ('season_crop'), ('season_events'),
        ('season_harvest'), ('season_cost_items')
     ) AS t(table_name)
WHERE to_regclass(format('public.%I', t.table_name)) IS NOT NULL
\gexec
SQL


# استثناء legacy صريح ومؤقّت للتطوير/الانتقال فقط. الافتراضي fail-closed بلا DDL runtime.
if [[ "${APP_ALLOW_SCHEMA_CREATE,,}" == "true" ]]; then
  echo "⚠ APP_ALLOW_SCHEMA_CREATE=true: منح CREATE مؤقّت لـ${APP_ROLE}; غير مسموح في production certification" >&2
  psql_exec -v app_role="$APP_ROLE" <<'SQL'
GRANT CREATE ON SCHEMA public TO :"app_role";
SQL
fi

# ─ دور التحكّم لدالّة resolve_ingest_source (SCOUT-INGEST-01 B1.2b) ─
# NOSUPERUSER + BYPASSRLS + SELECT على external_ingest_sources فقط، يملك الدالّة (SECURITY DEFINER).
# FORCE RLS يسري على المالك ⇒ مالك غير BYPASS يُجوّع resolver. أقلّ سطح تصعيد. راجع ...B1.2b §1.1.
echo "─ دور التحكّم sahool_ingest_resolver (NOSUPERUSER BYPASSRLS، مالك الدالّة فقط) ─"
psql_exec <<'SQL'
SELECT format('CREATE ROLE %I NOLOGIN', 'sahool_ingest_resolver')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_ingest_resolver')
\gexec

ALTER ROLE sahool_ingest_resolver NOLOGIN NOSUPERUSER NOINHERIT BYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT USAGE ON SCHEMA public TO sahool_ingest_resolver;

DO $$
BEGIN
  IF to_regclass('public.external_ingest_sources') IS NOT NULL THEN
    GRANT SELECT ON external_ingest_sources TO sahool_ingest_resolver;
  END IF;
  IF to_regprocedure('public.resolve_ingest_source(text)') IS NOT NULL THEN
    EXECUTE 'ALTER FUNCTION resolve_ingest_source(TEXT) OWNER TO sahool_ingest_resolver';
  END IF;
  -- B1.3: دالّتا الإسقاط DEFINER يملكهما resolver (تحدّثان projection_status عابراً للمستأجرين).
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
# EXECUTE لـapp_role مُغطّى بـ"GRANT EXECUTE ON ALL FUNCTIONS ... TO app_role" أعلاه (الهجرات قبل bootstrap).

# ─ دور خدمة الإدخال sahool_ingest (SCOUT-INGEST-01 B1.2b — scout-ingest-service) ─
# أقلّ منح: SELECT+INSERT على external_submissions + EXECUTE resolver. NOBYPASSRLS · لا UPDATE/DELETE.
echo "─ دور خدمة الإدخال sahool_ingest (NOBYPASSRLS، SELECT+INSERT فقط) ─"
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
  -- B1.3: نموذج القراءة المملوك + دالّتا الإسقاط (التحديث عبر DEFINER فقط، لا UPDATE مباشر).
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
  -- SEASON-ENTRY-EVENTS-UI: منح SELECT على الـVIEW المُشتقّ للأهليّة (نقطة detail تقرأه؛ security_invoker).
  IF to_regclass('public.season_calibration_eligibility') IS NOT NULL THEN
    GRANT SELECT ON season_calibration_eligibility TO sahool_ingest;
  END IF;
END $$;
SQL

echo "─ إنشاء دور المهامّ الخلفيّة (${JOBS_ROLE} — BYPASSRLS لمسار الوظائف فقط) ─"
psql_exec -v jobs_role="$JOBS_ROLE" -v jobs_pw="$JOBS_PASSWORD" <<'SQL'
-- HIGH-002: المرسِل (event_outbox→NATS) والمجدوِل (الطقس) يقرآن عابراً للمستأجرين
-- بلا app.current_tenant بالتصميم. تحت RLS الجديدة على تلك الجداول، يحتاجان دوراً
-- يتجاوز RLS. هذا الدور مخصّص لهما عبر JOBS_DATABASE_URL — التطبيق يبقى على sahool_app
-- المعزول. (لا CREATEDB/CREATEROLE/SUPERUSER — أضيق صلاحيّة تُنجز المهمّة.)
SELECT format('CREATE ROLE %I LOGIN', :'jobs_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'jobs_role')
\gexec

ALTER ROLE :"jobs_role"
  LOGIN NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'jobs_pw';

GRANT USAGE ON SCHEMA public TO :"jobs_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"jobs_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"jobs_role";
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO :"jobs_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"jobs_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"jobs_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO :"jobs_role";
SQL


# ── سحب CONNECT الضمنيّ من PUBLIC + منح صريح للأدوار المُدارة ──
# PostgreSQL يمنح CONNECT على أيّ قاعدة جديدة لـPUBLIC افتراضيًّا — أيّ دور
# يُنشأ لاحقًا (كـodoo_app) يتّصل بالمنصّة تلقائيًّا ويهزم أيّ REVOKE موجَّه.
# نسحب الامتياز الضمنيّ ونمنح CONNECT صراحةً للأدوار المُدارة فقط.
echo "─ سحب CONNECT من PUBLIC + منح صريح للأدوار المُدارة ─"
psql_exec -v dbname="$PGDATABASE" -v app_role="$APP_ROLE" -v jobs_role="$JOBS_ROLE" <<'SQL'
REVOKE CONNECT ON DATABASE :"dbname" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"dbname" TO :"app_role";
GRANT CONNECT ON DATABASE :"dbname" TO :"jobs_role";
GRANT CONNECT ON DATABASE :"dbname" TO sahool_ingest;
SQL

# ── دور Odoo المقيَّد (DB-P0-03) ──
ODOO_ROLE="${ODOO_DB_ROLE:-odoo_app}"
ODOO_ROLE_PW="${ODOO_DB_PASSWORD:-odoo_app_pw}"
echo "─ دور Odoo المقيَّد (${ODOO_ROLE} — لا اتّصال بقواعد المنصّة) ─"
# Odoo كان يعمل باعتماد مالك الهجرات (sahool_user superuser) — اختراق ERP كان
# يعني المنصّة كلّها. هذا الدور: CREATEDB فقط (لينشئ sahool_erp عبر odoo-init)،
# مسحوب منه كلّ امتيازات قاعدة المنصّة، وبلا BYPASSRLS/SUPERUSER.
psql_exec -v dbname="$PGDATABASE" -v odoo_role="$ODOO_ROLE" -v odoo_pw="$ODOO_ROLE_PW" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'odoo_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'odoo_role')
\gexec

ALTER ROLE :"odoo_role"
  LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS CREATEDB NOCREATEROLE PASSWORD :'odoo_pw';

-- حاسم: سحب **كلّ** امتيازات قاعدة المنصّة (لا CONNECT فقط — REVOKE CONNECT
-- وحده يُبقي أيّ منح سابقة وTEMP). CREATEDB يكفيه: sahool_erp التي ينشئها
-- يملكها تلقائيًّا فتُمنح له كلّ صلاحيّاتها.
REVOKE ALL PRIVILEGES ON DATABASE :"dbname" FROM :"odoo_role";
SQL

# ── تأكيد bootstrap: لا SUPERUSER/BYPASSRLS خارج القائمة المعتمدة ──
# يكشف أيّ انجراف يدويّ (ALTER ROLE ... BYPASSRLS خارج هذا السكربت) منذ الإقلاع
# الأوّل. BYPASSRLS معتمد فقط لدور المهامّ (عابر مستأجرين بالتصميم) وresolver
# (مالك دوالّ DEFINER). متغيّرات psql لا تُستبدَل داخل DO $$…$$ — نمرّر عبر GUC.
echo "─ تأكيد سمات الأدوار المُدارة (SUPERUSER/BYPASSRLS) ─"
MANAGED_CSV="${APP_ROLE},${JOBS_ROLE},sahool_ingest,sahool_ingest_resolver,${ODOO_ROLE}"
BYPASS_OK_CSV="${JOBS_ROLE},sahool_ingest_resolver"
psql_exec -v managed="$MANAGED_CSV" -v bypass_ok="$BYPASS_OK_CSV" <<'SQL'
SET app.managed_roles = :'managed';
SET app.bypassrls_allowed = :'bypass_ok';
DO $$
DECLARE bad text;
BEGIN
  SELECT string_agg(r.rolname, ', ') INTO bad
  FROM pg_roles r
  WHERE r.rolname = ANY (string_to_array(current_setting('app.managed_roles'), ','))
    AND (r.rolsuper OR r.rolbypassrls)
    AND NOT (r.rolname = ANY (string_to_array(current_setting('app.bypassrls_allowed'), ',')));
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'bootstrap assertion فشل: أدوار مُدارة تحمل SUPERUSER/BYPASSRLS خارج المعتمد: %', bad;
  END IF;
END $$;
SQL

echo "✓ التهيئة اكتملت — الهجرات مُطبَّقة، ودورا ${APP_ROLE} (تطبيق) و${JOBS_ROLE} (مهامّ) جاهزان."
