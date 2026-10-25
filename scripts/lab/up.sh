#!/usr/bin/env bash
# Start the Sahool local integration lab: PostGIS + Redis on the CI ports, the
# migrations applied twice, and a fresh venv from tests_v9/requirements-test.txt.
#
#   bash scripts/lab/up.sh        # then scripts/lab/run.sh, then scripts/lab/down.sh
#
# Every step either succeeds or exits non-zero with a named cause; nothing is
# reused from a previous lab unless its digest or requirements hash matches.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/lab/lab.env
source scripts/lab/lab.env
mkdir -p "$LAB_DIR"

fail() { echo "::error::$1" >&2; exit 1; }

# 1) Docker daemon. Started only when it is absent and this user may start it.
if ! docker info >/dev/null 2>&1; then
  command -v dockerd >/dev/null || fail "LAB_DOCKER_UNAVAILABLE: no daemon and no dockerd"
  setsid nohup dockerd >"$LAB_DIR/dockerd.log" 2>&1 </dev/null &
  for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 1; done
  docker info >/dev/null 2>&1 || fail "LAB_DOCKER_START_FAILED: see $LAB_DIR/dockerd.log"
fi

# 2) Images by digest, from the first registry that serves that digest.
pull_pinned() {  # $1 = image path, $2 = digest; prints the local reference
  local path="$1" digest="$2" registry ref
  for registry in $LAB_REGISTRIES; do
    ref="$registry/$path@$digest"
    if timeout 600 docker pull -q "$ref" >/dev/null 2>&1 &&
      docker image inspect "$ref" --format '{{json .RepoDigests}}' | grep -q "@$digest\""; then
      echo "$ref"
      return 0
    fi
    echo "pull $ref failed; trying the next registry" >&2
  done
  return 1
}
pg_ref="$(pull_pinned "$LAB_PG_IMAGE_PATH" "$LAB_PG_IMAGE_DIGEST")" ||
  fail "LAB_IMAGE_PULL_FAILED: $LAB_PG_IMAGE_PATH@$LAB_PG_IMAGE_DIGEST"
redis_ref="$(pull_pinned "$LAB_REDIS_IMAGE_PATH" "$LAB_REDIS_IMAGE_DIGEST")" ||
  fail "LAB_IMAGE_PULL_FAILED: $LAB_REDIS_IMAGE_PATH@$LAB_REDIS_IMAGE_DIGEST"
printf '%s\n%s\n' "$pg_ref" "$redis_ref" >"$LAB_DIR/image_refs.txt"

# 3) Containers. A lab container left from a previous run is replaced, never reused.
for c in "$LAB_PG_CONTAINER" "$LAB_REDIS_CONTAINER"; do
  if docker container inspect "$c" >/dev/null 2>&1; then
    docker container inspect "$c" --format '{{index .Config.Labels "sahool.lab"}}' |
      grep -qx integration || fail "LAB_NAME_TAKEN: $c exists without the lab label"
    docker rm -f "$c" >/dev/null
  fi
done
docker run -d --name "$LAB_PG_CONTAINER" --label "$LAB_LABEL" \
  -e POSTGRES_DB="$LAB_PG_DB" -e POSTGRES_USER="$LAB_PG_USER" \
  -e POSTGRES_PASSWORD="$LAB_PG_PASSWORD" \
  -p "127.0.0.1:$LAB_PG_PORT:5432" --pull=never "$pg_ref" >/dev/null
docker run -d --name "$LAB_REDIS_CONTAINER" --label "$LAB_LABEL" \
  -p "127.0.0.1:$LAB_REDIS_PORT:6379" --pull=never "$redis_ref" >/dev/null

# 4) Readiness: measured from inside each container, then from the host.
ready=""
for _ in $(seq 1 60); do
  if docker exec "$LAB_PG_CONTAINER" pg_isready -h 127.0.0.1 -U "$LAB_PG_USER" -d "$LAB_PG_DB" >/dev/null 2>&1 &&
    PGPASSWORD="$LAB_PG_PASSWORD" psql -X -h 127.0.0.1 -p "$LAB_PG_PORT" -U "$LAB_PG_USER" \
      -d "$LAB_PG_DB" -Atc 'select 1' 2>/dev/null | grep -qx 1; then
    ready=1
    break
  fi
  sleep 1
done
[ -n "$ready" ] || fail "LAB_POSTGRES_NOT_READY"
for _ in $(seq 1 30); do
  docker exec "$LAB_REDIS_CONTAINER" redis-cli ping 2>/dev/null | grep -qx PONG && break
  sleep 1
done
docker exec "$LAB_REDIS_CONTAINER" redis-cli ping | grep -qx PONG || fail "LAB_REDIS_NOT_READY"

# 5) Migrations, twice: the second run measures idempotency, as in CI.
for pass in 1 2; do
  PGPASSWORD="$LAB_PG_PASSWORD" bash scripts/ci/apply_migration_manifest.sh \
    --host 127.0.0.1 --port "$LAB_PG_PORT" --user "$LAB_PG_USER" --db "$LAB_PG_DB" \
    >"$LAB_DIR/migrations_pass$pass.log" 2>&1 ||
    fail "LAB_MIGRATIONS_FAILED (pass $pass): see $LAB_DIR/migrations_pass$pass.log"
done
tables="$(PGPASSWORD="$LAB_PG_PASSWORD" psql -X -h 127.0.0.1 -p "$LAB_PG_PORT" -U "$LAB_PG_USER" \
  -d "$LAB_PG_DB" -Atc "select count(*) from information_schema.tables where table_schema='public'")"
[ "$tables" -gt 0 ] || fail "LAB_MIGRATIONS_APPLIED_NOTHING"

# 6) Test venv from the repo's pinned requirements; rebuilt when they change.
# edge-tts is the one package the CI job installs outside requirements-test.txt
# ("Install audited Edge transport for TTS egress acceptance"); the TTS boundary
# tests fail without it.
LAB_EDGE_TTS="edge-tts==7.2.8"
req_hash="$( (cat tests_v9/requirements-test.txt constraints-ci-tools.txt; echo "$LAB_EDGE_TTS") | sha256sum | cut -c1-64)"
venv="$LAB_DIR/venv"
if [ "$(cat "$venv/.requirements-sha256" 2>/dev/null)" != "$req_hash" ]; then
  rm -rf "$venv"
  "$LAB_PYTHON" -m venv "$venv"
  "$venv/bin/python" -m pip install -q --upgrade pip >"$LAB_DIR/pip.log" 2>&1
  (cd tests_v9 && "$venv/bin/python" -m pip install -q -r requirements-test.txt) \
    >>"$LAB_DIR/pip.log" 2>&1 || fail "LAB_VENV_INSTALL_FAILED: see $LAB_DIR/pip.log"
  "$venv/bin/python" -m pip install -q "$LAB_EDGE_TTS" >>"$LAB_DIR/pip.log" 2>&1 ||
    fail "LAB_VENV_INSTALL_FAILED: $LAB_EDGE_TTS"
  echo "$req_hash" >"$venv/.requirements-sha256"
fi

echo "lab up: pg=$pg_ref redis=$redis_ref tables=$tables venv=$venv"
