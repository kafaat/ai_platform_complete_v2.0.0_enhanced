#!/usr/bin/env bash
# Legacy TiTiler image through the S3 endpoint gate, against a disposable MinIO.
# Runs in CI (ci.yml, Raster Service Tests) and locally; never against a shared store.
# Proves inside the real container: refusal before uvicorn starts, a COG read through
# /vsis3/ despite stale GDAL values, SIGTERM reaching uvicorn as PID 1, no secret in logs.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if ! command -v docker >/dev/null 2>&1; then
  echo 'NOT_RUN_DOCKER_UNAVAILABLE: no Docker binary; this is NOT a passing integration test' >&2
  exit 3
fi
if ! docker compose version >/dev/null 2>&1; then
  echo 'NOT_RUN_DOCKER_COMPOSE_UNAVAILABLE: install Docker Compose plugin' >&2
  exit 3
fi
if ! docker info >/dev/null 2>&1; then
  echo 'NOT_RUN_DOCKER_DAEMON_UNAVAILABLE: Docker CLI present but no reachable daemon; NOT a pass' >&2
  exit 3
fi
: "${S3_TEST_MINIO_IMAGE:=coollabsio/minio:2025-04-22T22-12-26Z@sha256:a4938f37f1be1841b8e7b627ad0207b265345fd0d063e42d7410c78af0e63e68}"
: "${S3_TEST_TITILER_IMAGE:=ghcr.io/developmentseed/titiler:0.18.6@sha256:ab05b8d0b18155f3d43570a200c3205617419d5276593377ce48f96810aa8992}"
for image in "$S3_TEST_MINIO_IMAGE" "$S3_TEST_TITILER_IMAGE"; do
  if [[ ! "$image" =~ @sha256:[0-9a-f]{64}$ ]]; then
    echo 'NOT_RUN_UNPINNED_IMAGE: specify image@sha256:<64 lowercase hex>' >&2
    exit 3
  fi
done
free_port() { python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'; }
: "${S3_TEST_ROOT_USER:=sahool-titiler-acceptance}"
: "${S3_TEST_ROOT_PASSWORD:=$(python3 -c 'import secrets; print(secrets.token_urlsafe(28))')}"
: "${S3_TEST_HOST_PORT:=$(free_port)}"
: "${S3_TEST_TITILER_PORT:=$(free_port)}"
: "${S3_TEST_PROJECT:=sahool-titiler-gate-$(python3 -c 'import secrets; print(secrets.token_hex(4))')}"
export S3_TEST_MINIO_IMAGE S3_TEST_TITILER_IMAGE S3_TEST_ROOT_USER S3_TEST_ROOT_PASSWORD
export S3_TEST_HOST_PORT S3_TEST_TITILER_PORT S3_TEST_PROJECT
COMPOSE="$ROOT/tests/integration/s3_titiler_gate.compose.yml"
dc() { docker compose -p "$S3_TEST_PROJECT" -f "$COMPOSE" --profile sentinel "$@"; }
EVIDENCE="$(mktemp)"
cleanup() {
  dc down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -f "$EVIDENCE"
}
trap cleanup EXIT INT TERM

# Every phase's output lands in $EVIDENCE (a temp file, never uploaded); the secret
# scan reads it without printing it, and anything echoed on failure is redacted first.
redact() { local text="$1"; printf '%s\n' "${text//"$S3_TEST_ROOT_PASSWORD"/[redacted]}"; }
docker pull -q "$S3_TEST_TITILER_IMAGE" >/dev/null
# The pinned digest must be what the runner pulled; record what it actually runs.
PINNED_DIGEST="${S3_TEST_TITILER_IMAGE##*@}"
REPO_DIGESTS="$(docker image inspect --format '{{json .RepoDigests}}' "$S3_TEST_TITILER_IMAGE")"
if ! grep -qF "@${PINNED_DIGEST}" <<<"$REPO_DIGESTS"; then
  echo "TITILER_IMAGE_DIGEST_MISMATCH: pulled image does not carry ${PINNED_DIGEST}" >&2
  exit 2
fi
printf 'TiTiler image: repo_digests=%s arch=%s/%s id=%s entrypoint=%s cmd=%s user=%s\n' \
  "$REPO_DIGESTS" \
  "$(docker image inspect --format '{{.Os}}' "$S3_TEST_TITILER_IMAGE")" \
  "$(docker image inspect --format '{{.Architecture}}' "$S3_TEST_TITILER_IMAGE")" \
  "$(docker image inspect --format '{{.Id}}' "$S3_TEST_TITILER_IMAGE")" \
  "$(docker image inspect --format '{{json .Config.Entrypoint}}' "$S3_TEST_TITILER_IMAGE")" \
  "$(docker image inspect --format '{{json .Config.Cmd}}' "$S3_TEST_TITILER_IMAGE")" \
  "$(docker image inspect --format '{{.Config.User}}' "$S3_TEST_TITILER_IMAGE")"
# The tested platform must be the runner's: an emulated or foreign-arch image proves nothing here.
case "$(uname -m)" in
  x86_64) HOST_ARCH=amd64 ;;
  aarch64 | arm64) HOST_ARCH=arm64 ;;
  *) HOST_ARCH="$(uname -m)" ;;
esac
IMAGE_ARCH="$(docker image inspect --format '{{.Architecture}}' "$S3_TEST_TITILER_IMAGE")"
if [[ "$IMAGE_ARCH" != "$HOST_ARCH" ]]; then
  echo "TITILER_IMAGE_PLATFORM_MISMATCH: image=${IMAGE_ARCH} runner=${HOST_ARCH}" >&2
  exit 2
fi

# The sentinel stands in for every refused host (TCP 9000) until MinIO starts. Readiness
# is read from its log, never by connecting, so only the control can move the counter.
# Scope of the claim: no TCP connection to these names on port 9000; not all egress.
dc up -d sahool-endpoint-sentinel >/dev/null
for _ in $(seq 1 60); do
  dc logs --no-color sahool-endpoint-sentinel 2>/dev/null | grep -q SENTINEL_LISTENING && break
  sleep 1
done
if ! dc logs --no-color sahool-endpoint-sentinel 2>/dev/null | grep -q SENTINEL_LISTENING; then
  echo 'TITILER_SENTINEL_NOT_READY: the listener never started' >&2
  exit 2
fi
sentinel_connections() { dc logs --no-color sahool-endpoint-sentinel 2>/dev/null | grep -c SENTINEL_CONNECTION || true; }
# A count is accepted only once two reads a second apart agree (log delivery can lag).
stable_connections() {
  local previous current
  previous="$(sentinel_connections)"
  for _ in 1 2 3 4 5; do
    sleep 1
    current="$(sentinel_connections)"
    [[ "$current" == "$previous" ]] && { printf '%s\n' "$current"; return 0; }
    previous="$current"
  done
  echo 'TITILER_SENTINEL_COUNT_UNSTABLE' >&2
  exit 2
}
# Both names must resolve, inside the Compose network, to the sentinel and nothing else
# (IPv4 or IPv6), or a refusal could have gone somewhere the counter does not see.
SENTINEL_IP="$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  "$(dc ps -q sahool-endpoint-sentinel)")"
resolved="$(dc run --rm -T --no-deps --entrypoint python sahool-titiler -c \
  "import socket
for name in ('sahool-minio', 'objects.example.test'):
    print('DNS', name, ' '.join(sorted({a[4][0] for a in socket.getaddrinfo(name, 9000)})))" 2>&1)"
for name in sahool-minio objects.example.test; do
  if ! grep -qx "DNS ${name} ${SENTINEL_IP}" <<<"$resolved"; then
    echo "TITILER_SENTINEL_DNS_MISMATCH: ${name} does not resolve only to the sentinel" >&2
    redact "$resolved" | tail -5 >&2
    exit 2
  fi
done
echo "refused names resolve only to the sentinel (${SENTINEL_IP})"
if [[ "$(stable_connections)" != "0" ]]; then
  echo 'TITILER_SENTINEL_PRECONTACTED: connections before the control' >&2
  exit 2
fi

# 0) Positive control inside the image: replace `command` with a probe. The service
# environment carries stale values (stale-endpoint.invalid / YES / TRUE), so the exact
# line below can only come from the gate having run the policy and then exec-ed the
# probe; the probe run directly would print the stale values. It also opens one TCP
# connection to sahool-minio:9000, which proves the sentinel counts connections.
set +e
probe="$(dc run --rm -T --no-deps -e S3_ALLOW_PLAINTEXT_INTERNAL=true sahool-titiler \
  python -c "import os, socket; print('GDAL', os.environ['AWS_S3_ENDPOINT'], os.environ['AWS_HTTPS'], os.environ['AWS_VIRTUAL_HOSTING']); socket.create_connection(('sahool-minio', 9000), 5).close()" 2>&1)"
status=$?
set -e
printf '%s\n' "$probe" >>"$EVIDENCE"
if [[ "$status" != "0" ]] || ! grep -qx 'GDAL sahool-minio:9000 NO FALSE' <<<"$probe"; then
  echo "TITILER_GATE_CONTROL_FAILED: status=${status}; command override must still pass the gate" >&2
  redact "$probe" | tail -20 >&2
  exit 2
fi
echo 'command override still gated: GDAL sahool-minio:9000 NO FALSE'
CONTROL_COUNT="$(stable_connections)"
if [[ "$CONTROL_COUNT" != "1" ]]; then
  echo "TITILER_SENTINEL_BLIND: expected the control's single connection, got ${CONTROL_COUNT}" >&2
  exit 2
fi
echo 'sentinel saw the control connection: 1'

# 1) Refusals inside the real image: the gate exits 78 before uvicorn ever starts.
expect_refusal() {
  local code="$1" hidden="$2"; shift 2
  local out status before after
  before="$(stable_connections)"
  set +e
  out="$(dc run --rm -T --no-deps "$@" sahool-titiler 2>&1)"
  status=$?
  set -e
  printf '%s\n' "$out" >>"$EVIDENCE"
  # Only the gate prints this exact line, and only with this fixed code.
  if [[ "$status" != "78" ]] || ! grep -qx "unsafe S3 endpoint configuration: ${code}" <<<"$out"; then
    echo "TITILER_GATE_REFUSAL_FAILED: expected exit 78 with ${code}, got status=${status}" >&2
    redact "$out" | tail -20 >&2
    exit 2
  fi
  if grep -qi "uvicorn running\|started server process" <<<"$out"; then
    echo "TITILER_GATE_REFUSAL_FAILED: uvicorn started despite ${code}" >&2
    exit 2
  fi
  if grep -qF "$hidden" <<<"$out"; then
    echo "TITILER_GATE_ECHOED_INPUT: the refusal for ${code} repeats the configured endpoint" >&2
    exit 2
  fi
  # Per case, so a leak names the case that caused it.
  after="$(stable_connections)"
  if [[ "$after" != "$before" ]]; then
    echo "TITILER_REFUSED_HOST_CONTACTED: ${code} reached the sentinel (${before} -> ${after})" >&2
    exit 2
  fi
  printf 'refused before start, no connection: %s\n' "$code"
}
expect_refusal plaintext_internal_requires_opt_in sahool-minio:9000
expect_refusal plaintext_external_forbidden objects.example.test \
  -e S3_ENDPOINT=http://objects.example.test:9000 -e S3_ALLOW_PLAINTEXT_INTERNAL=true
expect_refusal scheme_flag_conflict sahool-minio:9000 \
  -e S3_ENDPOINT=https://sahool-minio:9000 -e S3_USE_SSL=false
expect_refusal endpoint_must_be_host_only /rasters \
  -e S3_ENDPOINT=http://sahool-minio:9000/rasters -e S3_ALLOW_PLAINTEXT_INTERNAL=true
# Total after the four cases: still only the control's connection. Stop it only now.
if [[ "$(stable_connections)" != "$CONTROL_COUNT" ]]; then
  echo 'TITILER_REFUSED_HOST_CONTACTED: total moved after the refusals' >&2
  exit 2
fi
echo 'refused endpoints received no connection on TCP 9000'
dc rm -sf sahool-endpoint-sentinel >/dev/null

# 2) Accepted path: MinIO, a synthetic COG, then TiTiler with the internal opt-in.
dc up -d --wait --wait-timeout 90 sahool-minio
export SAHOOL_S3_ACCEPTANCE_DISPOSABLE=1
python3 "$ROOT/scripts/ci/s3_titiler_gate_live_acceptance.py" upload \
  --endpoint "http://127.0.0.1:${S3_TEST_HOST_PORT}"
S3_TEST_ALLOW_PLAINTEXT_INTERNAL=true dc up -d --wait --wait-timeout 120 sahool-titiler
REPORT="${S3_TEST_REPORT:-${TMPDIR:-/tmp}/sahool-titiler-${S3_TEST_PROJECT}.json}"
python3 "$ROOT/scripts/ci/s3_titiler_gate_live_acceptance.py" read \
  --titiler "http://127.0.0.1:${S3_TEST_TITILER_PORT}" --report "$REPORT" | tee -a "$EVIDENCE"

# 3) exec: uvicorn is PID 1, so SIGTERM from `stop` ends it cleanly (exit 0, not 137).
CONTAINER_ID="$(dc ps -q sahool-titiler)"
PID1="$(docker exec "$CONTAINER_ID" cat /proc/1/cmdline | tr '\0' ' ')"
if [[ "$PID1" != *uvicorn* || "$PID1" == *gdal_s3_env_gate* ]]; then
  echo "TITILER_GATE_NOT_EXECED: PID 1 is not uvicorn" >&2
  exit 2
fi
echo 'PID 1 is uvicorn (the gate exec-ed itself away)'
dc stop -t 20 sahool-titiler >/dev/null
EXIT_CODE="$(docker inspect --format '{{.State.ExitCode}}' "$CONTAINER_ID")"
if [[ "$EXIT_CODE" != "0" ]]; then
  echo "TITILER_SIGTERM_NOT_FORWARDED: exit code ${EXIT_CODE} after stop" >&2
  exit 2
fi
echo 'SIGTERM reached uvicorn: exit 0'

# 4) The test-only root password reaches neither logs, refusals nor the report.
# grep -q never prints the match; only file names are reported.
dc logs --no-color >>"$EVIDENCE" 2>&1
for source in "$EVIDENCE" "$REPORT"; do
  if grep -qF -- "$S3_TEST_ROOT_PASSWORD" "$source"; then
    echo "TITILER_SECRET_IN_EVIDENCE: test root password found in $(basename "$source")" >&2
    exit 2
  fi
done
echo 'no secret in logs, refusals or report'
