#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# odoo-init.sh — نقطة دخول ذاتيّة‑التعافي لـOdoo (SAHOOL)
#
# المشكلة (مُتحقّق منها أثناء التشغيل): قد تُنشَأ قاعدة Odoo (sahool_erp) دون أن
# تُهيَّأ — أي لا تُثبَّت وحدة base — فتدخل في حلقة فشل على /web/login:
#   relation "ir_module_module" does not exist  /  KeyError: 'ir.http'.
# والسبب أنّ `command` السابق كان يُمرّر `-i base` في كلّ إقلاع (يُعيد التثبيت
# عبثاً) ولا يُنشئ القاعدة ولا يتعافى من تهيئة جزئيّة.
#
# الحلّ (idempotent + self‑healing):
#   1) انتظِر Postgres (pg_isready) متسامحاً مع الأعطال العابرة.
#   2) أنشئ قاعدة Odoo (createdb) إن غابت — منفصلة عن قاعدة المنصّة «sahool» (RLS).
#   3) اكشِف هل base مُثبَّتة فعلاً عبر to_regclass('public.ir_module_module').
#   4) إن لم تكن مُثبَّتة → ثبِّتها مرّة واحدة بـ--stop-after-init.
#   5) ثمّ exec للعمليّة الطويلة بلا أيّ `-i` (لا إعادة تثبيت عند كلّ إقلاع).
#
# يقرأ الإعداد من البيئة نفسها التي يستهلكها entrypoint صورة odoo:17:
#   ODOO_DB (افتراضي sahool_erp) و HOST/PORT/USER/PASSWORD.
# صورة odoo:17 تتضمّن postgresql-client (psql/createdb/pg_isready).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── الإعداد من البيئة (مع قيم افتراضيّة آمنة) ───────────────────────────────
ODOO_DB="${ODOO_DB:-sahool_erp}"
DB_HOST="${HOST:-${DB_HOST:-db}}"
DB_PORT="${PORT:-${DB_PORT:-5432}}"
DB_USER="${USER:-${DB_USER:-odoo}}"
DB_PASSWORD="${PASSWORD:-${DB_PASSWORD:-}}"

# createdb/psql يقرآن كلمة المرور من PGPASSWORD (لا نمرّرها على سطر الأوامر).
export PGPASSWORD="${DB_PASSWORD}"
export PGHOST="${DB_HOST}"
export PGPORT="${DB_PORT}"
export PGUSER="${DB_USER}"

# ── 1) انتظار Postgres مع تسامح مع الأعطال العابرة ──────────────────────────
echo "[odoo-init] في انتظار Postgres على ${DB_HOST}:${DB_PORT} (المستخدم ${DB_USER})…"
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" >/dev/null 2>&1; do
  echo "[odoo-init] Postgres غير جاهز بعد — إعادة المحاولة خلال ثانيتين…"
  sleep 2
done
echo "[odoo-init] Postgres جاهز."

# ── 2) إنشاء قاعدة Odoo إن غابت (منفصلة عن قاعدة المنصّة sahool) ─────────────
# psql -d postgres لتفادي الاتصال بقاعدة قد لا توجد بعد.
db_exists="$(psql -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname = '${ODOO_DB}'" 2>/dev/null || true)"
if [ "${db_exists}" != "1" ]; then
  echo "[odoo-init] القاعدة «${ODOO_DB}» غير موجودة — إنشاؤها…"
  # --encoding/--lc-collate=C يطابق متطلّبات Odoo (تفادي مشاكل الترتيب).
  createdb --encoding=UTF8 --lc-collate=C --lc-ctype=C --template=template0 "${ODOO_DB}"
  echo "[odoo-init] أُنشئت القاعدة «${ODOO_DB}»."
else
  echo "[odoo-init] القاعدة «${ODOO_DB}» موجودة."
fi

# ── 3) كشف هل base مُثبَّتة فعلاً (وجود الجدول ir_module_module) ──────────────
# to_regclass تُرجع NULL إذا غاب الجدول — مؤشّر دقيق على تهيئة جزئيّة/مفقودة.
base_installed="$(psql -d "${ODOO_DB}" -tAc \
  "SELECT to_regclass('public.ir_module_module') IS NOT NULL" 2>/dev/null || echo 'f')"

# ── 4) تثبيت base مرّة واحدة فقط عند الحاجة ──────────────────────────────────
if [ "${base_installed}" != "t" ]; then
  echo "[odoo-init] base غير مُثبَّتة (القاعدة مُنشأة لكن غير مُهيّأة) — تثبيتها الآن…"
  odoo -d "${ODOO_DB}" -i base --without-demo=all \
       --db-filter="^${ODOO_DB}\$" --stop-after-init
  echo "[odoo-init] اكتمل تثبيت base."
else
  echo "[odoo-init] base مُثبَّتة مسبقاً — تخطّي التثبيت."
fi

# ── 5) العمليّة الطويلة بلا -i (لا إعادة تثبيت عند كلّ إقلاع) ─────────────────
echo "[odoo-init] إقلاع Odoo (العمليّة الطويلة) على القاعدة «${ODOO_DB}»…"
exec odoo -d "${ODOO_DB}" --without-demo=all --db-filter="^${ODOO_DB}\$"
