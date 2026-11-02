#!/usr/bin/env bash
# migration-dsn-env.sh — مُحوِّلٌ رفيع لمهمّة الهجرة في helm (يُركَّب من ConfigMap).
#
# يشتقّ PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE (و PGSSL*) من السرّ JOBS_DATABASE_URL ثمّ
# يُسلِّم إلى مُشغّل الهجرات نفسه الذي يشغّله Railway (deploy/railway/Dockerfile.migrate →
# /migrations/apply_in_compose.sh). ذلك المُشغّل يقرأ متغيّرات PG* منفصلةً لا DSN، والسرّ في
# helm DSN واحد — فهذا الملفّ هو الفرق الوحيد بين المسارين. إذن التطبيق (SAHOOL_MIGRATE_APPLY)
# يمرّ كما هو ويبقى قرارُه للمُشغّل (I1، تدقيق 2026-11-01).
#
# الاستعمال: bash migration-dsn-env.sh <runner> [args...]
# لا يطبع أيّ قيمة اعتماد. DSN غير قابلٍ للتحليل أو بمعامِلٍ غير معروف ⇒ خروج 2 قبل أيّ اتّصال
# (معامِلٌ مُسقَطٌ بصمت مثل sslmode كان سيُخفِّض TLS دون أثر).
set -euo pipefail

fail() {
  echo "MIGRATIONS_NOT_APPLIED reason=$1" >&2
  exit 2
}

[ "$#" -ge 1 ] || fail runner_missing
dsn="${JOBS_DATABASE_URL:-}"
[ -n "$dsn" ] || fail dsn_missing

# فكّ ترميز النسبة (%XX) بلا تفسير الشرطة المائلة الخام: تُضاعَف أوّلاً ثمّ %XX ⇒ \xXX.
pct() {
  local s="${1//\\/\\\\}"
  printf '%b' "${s//%/\\x}"
}

# postgres[ql]://user[:password]@host[:port]/db[?k=v&...] — نفس حدود libpq: userinfo حتى '@'
# ولا '/' فيه. IPv6 بين أقواس وعدّة مضيفين غير مدعومين ⇒ رفض صريح لا تخمين.
re='^postgres(ql)?://([^:@/]+)(:([^@/]*))?@([^:/?@,]+)(:([0-9]+))?/([^?/]+)(\?(.*))?$'
[[ "$dsn" =~ $re ]] || fail dsn_unparseable
m_user="${BASH_REMATCH[2]}"
m_has_pw="${BASH_REMATCH[3]}"
m_pw="${BASH_REMATCH[4]}"
m_host="${BASH_REMATCH[5]}"
m_port="${BASH_REMATCH[7]}"
m_db="${BASH_REMATCH[8]}"
m_query="${BASH_REMATCH[10]}"

PGUSER="$(pct "$m_user")"
PGHOST="$(pct "$m_host")"
PGPORT="${m_port:-5432}"
PGDATABASE="$(pct "$m_db")"
export PGUSER PGHOST PGPORT PGDATABASE
if [ -n "$m_has_pw" ]; then
  PGPASSWORD="$(pct "$m_pw")"
  export PGPASSWORD
fi

if [ -n "$m_query" ]; then
  IFS='&' read -r -a kvs <<<"$m_query"
  for kv in "${kvs[@]}"; do
    [ -n "$kv" ] || continue
    [[ "$kv" == *=* ]] || fail "dsn_unsupported_param param=${kv}"
    k="${kv%%=*}"
    v="$(pct "${kv#*=}")"
    case "$k" in
      sslmode) export PGSSLMODE="$v" ;;
      sslrootcert) export PGSSLROOTCERT="$v" ;;
      sslcert) export PGSSLCERT="$v" ;;
      sslkey) export PGSSLKEY="$v" ;;
      connect_timeout) export PGCONNECT_TIMEOUT="$v" ;;
      application_name) export PGAPPNAME="$v" ;;
      *) fail "dsn_unsupported_param param=${k}" ;;
    esac
  done
fi

# الـDSN الخام لا يلزم المُشغّل بعد الاشتقاق — لا يُورَّث إلى psql وأبنائه.
unset JOBS_DATABASE_URL
exec bash "$@"
