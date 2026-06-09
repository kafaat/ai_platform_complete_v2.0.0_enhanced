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
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-sahool-postgres-dev}"
PG_IMAGE="postgis/postgis:15-3.4"
PG_PASSWORD="${PGPASSWORD:-sahool_dev_pw}"
PG_PORT="${PGPORT:-5432}"
PG_DB="${PGDATABASE:-sahool}"
PG_USER="${PGUSER:-sahool_user}"
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

echo ""
echo "═══ تمّ ✓ ═══"
echo "DATABASE_URL=postgresql://$PG_USER:$PG_PASSWORD@127.0.0.1:$PG_PORT/$PG_DB"
echo "للإيقاف:  docker rm -f $PG_CONTAINER"
