#!/usr/bin/env bash
# migrations/apply_in_compose.sh — يُطبَّق داخل خدمة sahool-migrate (postgis image).
# يُنفّذ MANIFEST.txt بالترتيب، ثمّ يُنشئ الأدوار التشغيليّة (sahool_app/sahool_jobs/sahool_ingest)
# ودور Odoo المقيَّد. idempotent — آمن على إعادة التشغيل.
set -euo pipefail

: "${PGHOST:?}"
: "${PGPORT:=5432}"
: "${PGUSER:?}"
: "${PGPASSWORD:?}"
: "${PGDATABASE:?}"

psql_exec() {
  psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1 "$@"
}

echo "== تطبيق الهجرات من MANIFEST.txt =="

# تثبيت امتدادات أساسيّة قبل أيّ migration يحتاجها.
psql_exec <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
SQL

APPLIED=0
SKIPPED=0
FAILED=0

while IFS= read -r line; do
  line="${line%%#*}"            # إزالة التعليقات
  line="$(echo "$line" | xargs)"  # تقليم الفراغات
  [ -z "$line" ] && continue
  case "$line" in *.sql) ;; *) continue ;; esac
  f="/migrations/$line"
  if [ ! -f "$f" ]; then
    echo "✗ migration مفقود: $line" >&2
    FAILED=$((FAILED+1))
    continue
  fi
  echo "→ $line"
  if psql_exec -f "$f" > /tmp/mig_out 2>&1; then
    APPLIED=$((APPLIED+1))
  else
    echo "✗ فشل $line:" >&2
    cat /tmp/mig_out >&2
    FAILED=$((FAILED+1))
  fi
done < /migrations/MANIFEST.txt

echo "== النتيجة: طُبِّق $APPLIED، فشل $FAILED =="
[ "$FAILED" -eq 0 ] || exit 1

echo "== الأدوار التشغيليّة =="

APP_ROLE="${APP_DB_ROLE:-sahool_app}"
APP_PW="${APP_DB_PASSWORD:-sahool_app_pw}"
JOBS_ROLE="${JOBS_DB_ROLE:-sahool_jobs}"
JOBS_PW="${JOBS_DB_PASSWORD:-sahool_jobs_pw}"
INGEST_PW="${INGEST_DB_PASSWORD:-sahool_ingest_pw}"

psql_exec -v app_role="$APP_ROLE" -v app_pw="$APP_PW" \
          -v jobs_role="$JOBS_ROLE" -v jobs_pw="$JOBS_PW" \
          -v ingest_pw="$INGEST_PW" <<'SQL'
-- sahool_app: دور runtime المقيَّد (NOBYPASSRLS — تُطبَّق عليه سياسات RLS).
SELECT format('CREATE ROLE %I LOGIN', :'app_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec

ALTER ROLE :"app_role"
  LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION
  PASSWORD :'app_pw';

-- DB-P0-01 (التدقيق الجنائيّ): كانت ALL TABLES + ALL FUNCTIONS (قراءة/تعديل كلّ شيء
-- بما فيه audit الأمنيّ). الحدّ الأدنى runtime: DML على الجداول + USAGE على
-- المخطّطات + EXECUTE على دوالّ set_config فقط (app.current_tenant وما شابه).
GRANT CONNECT ON DATABASE sahool TO :"app_role";
GRANT USAGE ON SCHEMA public TO :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_role";

-- sahool_jobs: معالجات طواريء النظام (BYPASSRLS مقصود وموثَّق — يتجاوز RLS).
SELECT format('CREATE ROLE %I LOGIN', :'jobs_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'jobs_role')
\gexec

ALTER ROLE :"jobs_role"
  LOGIN NOSUPERUSER NOINHERIT BYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION
  PASSWORD :'jobs_pw';

GRANT CONNECT ON DATABASE sahool TO :"jobs_role";
GRANT USAGE ON SCHEMA public TO :"jobs_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"jobs_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"jobs_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"jobs_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"jobs_role";

-- sahool_ingest: قناة الإدخال الخارجيّ (SELECT+INSERT فقط، NOBYPASSRLS).
SELECT format('CREATE ROLE sahool_ingest LOGIN')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_ingest')
\gexec

ALTER ROLE sahool_ingest
  LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION
  PASSWORD :'ingest_pw';

GRANT CONNECT ON DATABASE sahool TO sahool_ingest;
GRANT USAGE ON SCHEMA public TO sahool_ingest;
SQL

echo "─ دور Odoo المقيَّد (${ODOO_ROLE} — DB-P0-03: لا اتّصال بقواعد المنصّة) ─"
# Odoo كان يعمل باعتماد مالك الهجرات (sahool_user superuser) — اختراق ERP كان يعني
# المنصّة كلّها. هذا الدور: CREATEDB فقط (لينشئ sahool_erp عبر odoo-init)، ممنوع
# من CONNECT على قاعدة المنصّة، وبلا BYPASSRLS/SUPERUSER.
ODOO_ROLE="${ODOO_DB_ROLE:-odoo_app}"
ODOO_ROLE_PW="${ODOO_DB_PASSWORD:-odoo_app_pw}"
psql_exec -v odoo_role="$ODOO_ROLE" -v odoo_pw="$ODOO_ROLE_PW" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'odoo_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'odoo_role')
\gexec

ALTER ROLE :"odoo_role"
  LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS CREATEDB NOCREATEROLE PASSWORD :'odoo_pw';

-- حاسم: منع الاتّصال بقاعدة المنصّة (وأيّ قاعدة غير قاعدته). CREATEDB يكفيه
-- لإنشاء sahool_erp التي يملكها تلقائيًّا فتُمنح له كلّ صلاحيّاتها.
REVOKE CONNECT ON DATABASE sahool FROM :"odoo_role";
SQL

echo "✓ التهيئة اكتملت"
