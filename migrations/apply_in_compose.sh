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

-- صلاحيّات وقت التشغيل: DML + EXECUTE + USAGE
GRANT USAGE ON SCHEMA public TO :"app_role";
-- FINDING-001 collateral: بعض الخدمات تُنشئ جداولها (IF NOT EXISTS) عند الإقلاع
-- (مثل odoo-bridge _run_migrations). تحتاج CREATE على المخطّط. لا يمسّ عزل المستأجرين:
-- CREATE ليس BYPASSRLS — تبقى RLS سارية على كلّ الجداول (الخاصّيّة الحرجة محفوظة).
GRANT CREATE ON SCHEMA public TO :"app_role";
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

echo "✓ التهيئة اكتملت — الهجرات مُطبَّقة ودور ${APP_ROLE} جاهز (وجّه DATABASE_URL للتطبيق إليه)."
