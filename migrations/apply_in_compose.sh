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

echo "─ تطبيق الهجرات (ترتيب MANIFEST، لا أبجدي) على ${PGHOST}/${PGDATABASE} ─"
applied=0
while IFS= read -r f; do
  case "$f" in '' | \#*) continue ;; esac
  echo "  → $f"
  psql_exec -f "$MIG_DIR/$f" >/dev/null
  applied=$((applied + 1))
done < <(grep -vE '^\s*#|^\s*$' "$MIG_DIR/MANIFEST.txt")
echo "  ✓ طُبّقت $applied هجرة (idempotent — آمنة على التكرار)"

echo "─ إنشاء دور التطبيق المقيّد (${APP_ROLE} — NOSUPERUSER NOBYPASSRLS) ─"
psql_exec -v app_role="$APP_ROLE" -v app_pw="$APP_PASSWORD" <<'SQL'
-- ١) أنشئ الدور فقط إن لم يكن موجوداً (يُولّد SQL ثمّ يُنفّذ بـ\gexec)
SELECT format('CREATE ROLE %I LOGIN', :'app_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec

-- ٢) ثبّت السمات الأمنيّة وكلمة السرّ (idempotent سواء أُنشئ الآن أو سابقاً)
ALTER ROLE :"app_role"
  LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'app_pw';

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
SQL


# استثناء legacy صريح ومؤقّت للتطوير/الانتقال فقط. الافتراضي fail-closed بلا DDL runtime.
if [[ "${APP_ALLOW_SCHEMA_CREATE,,}" == "true" ]]; then
  echo "⚠ APP_ALLOW_SCHEMA_CREATE=true: منح CREATE مؤقّت لـ${APP_ROLE}; غير مسموح في production certification" >&2
  psql_exec -v app_role="$APP_ROLE" <<'SQL'
GRANT CREATE ON SCHEMA public TO :"app_role";
SQL
fi

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

echo "✓ التهيئة اكتملت — الهجرات مُطبَّقة، ودورا ${APP_ROLE} (تطبيق) و${JOBS_ROLE} (مهامّ) جاهزان."
