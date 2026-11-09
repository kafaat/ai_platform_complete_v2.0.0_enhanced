#!/usr/bin/env bash
# Expected: E3P_END status=0. Any unexpected acceptance is a FAIL, never a warning.
set -uo pipefail
: "${PGHOST:?}" "${PGPORT:?}" "${PGUSER:?}" "${PGPASSWORD:?}" "${PGDATABASE:?}"
status=0
ok()   { echo "E3P_PASS $*"; }
bad()  { echo "E3P_FAIL $*"; status=1; }
export PGCONNECT_TIMEOUT=10 PGSSLMODE=prefer
echo "E3P_BEGIN host=${PGHOST} db=${PGDATABASE} at=$(date -u +%FT%TZ)"
for i in $(seq 1 60); do pg_isready -h "$PGHOST" -p "$PGPORT" >/dev/null 2>&1 && break; sleep 2; done

# 1) correct password over TCP
if out=$(psql -X -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Atc "select version()" 2>&1); then
  ok "auth_correct_password"; echo "E3P_ENGINE ${out}"
  psql -X -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Atc "select 'E3P_POSTGIS ' || postgis_full_version()"
  psql -X -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Atc "select 'E3P_PASSWORD_ENCRYPTION ' || current_setting('password_encryption')"
  psql -X -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -At -F ' | ' -c \
    "select 'E3P_HBA', line_number, type, array_to_string(database,','), array_to_string(user_name,','), coalesce(address,'-'), auth_method from pg_hba_file_rules order by line_number"
  trust_tcp=$(psql -X -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Atc \
    "select count(*) from pg_hba_file_rules where auth_method='trust' and type <> 'local' and coalesce(address,'') not in ('127.0.0.1','::1')")
  [ "$trust_tcp" = "0" ] && ok "no_trust_rule_for_non_local_tcp" || bad "trust_rule_for_non_local_tcp count=${trust_tcp}"
else
  bad "auth_correct_password: ${out}"
fi

# 2) wrong password over TCP must be refused
wrong=$(openssl rand -hex 24)
if out=$(PGPASSWORD="$wrong" psql -X -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Atc "select 1" 2>&1); then
  bad "wrong_password_accepted"
else
  echo "$out" | grep -qi "password authentication failed" && ok "wrong_password_refused" || bad "wrong_password_unexpected_error: ${out}"
fi

# 3) no password over TCP must be refused
if out=$(env -u PGPASSWORD PGPASSFILE=/dev/null psql -X -w -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Atc "select 1" 2>&1); then
  bad "missing_password_accepted"
else
  echo "$out" | grep -qiE "password|no password supplied|authentication" && ok "missing_password_refused" || bad "missing_password_unexpected_error: ${out}"
fi

# 4) restricted role: can log in, cannot create a database, has no RLS bypass; dropped afterwards
rpw=$(openssl rand -hex 24)
psql -X -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v pw="$rpw" -v db="$PGDATABASE" >/dev/null <<'SQL'
SELECT format('CREATE ROLE e3_probe_ro LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT', :'pw') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO e3_probe_ro', :'db') \gexec
SQL
if who=$(PGPASSWORD="$rpw" psql -X -h "$PGHOST" -p "$PGPORT" -U e3_probe_ro -d "$PGDATABASE" -Atc "select current_user" 2>&1) && [ "$who" = "e3_probe_ro" ]; then
  ok "restricted_role_login"
  flags=$(psql -X -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Atc "select rolsuper::text||':'||rolcreatedb::text||':'||rolbypassrls::text from pg_roles where rolname='e3_probe_ro'")
  [ "$flags" = "false:false:false" ] && ok "restricted_role_flags ${flags}" || bad "restricted_role_flags ${flags}"
  if PGPASSWORD="$rpw" psql -X -h "$PGHOST" -p "$PGPORT" -U e3_probe_ro -d "$PGDATABASE" -Atc "create database e3_probe_should_fail" >/dev/null 2>&1; then
    bad "restricted_role_created_database"; psql -X -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "drop database if exists e3_probe_should_fail" >/dev/null
  else ok "restricted_role_cannot_create_database"; fi
else
  bad "restricted_role_login: ${who}"
fi
psql -X -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v db="$PGDATABASE" >/dev/null <<'SQL' && ok "restricted_role_dropped" || bad "restricted_role_drop"
SELECT format('REVOKE CONNECT ON DATABASE %I FROM e3_probe_ro', :'db') WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname='e3_probe_ro') \gexec
DROP ROLE IF EXISTS e3_probe_ro;
SQL
left=$(psql -X -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Atc "select count(*) from pg_roles where rolname='e3_probe_ro'")
[ "$left" = "0" ] && ok "no_probe_role_left" || bad "probe_role_left"
echo "E3P_END status=${status} at=$(date -u +%FT%TZ)"
exit "$status"
