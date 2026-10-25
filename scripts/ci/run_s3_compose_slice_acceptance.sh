#!/usr/bin/env bash
# S3 slice of docker-compose.v9.yml, booted from its real service definitions, with no
# database, no migrator and no migration (incident freeze): sahool-minio + sahool-minio-init
# (buckets and per-service keys), sahool-raster-service, sahool-scout-ingest's image and the
# legacy-tiler profile. Synthetic credentials only, generated per run and never printed.
#
# Proves on the checked-out SHA: the deliberate compatibility break (refusal at startup
# without S3_ALLOW_PLAINTEXT_INTERNAL), recovery with it, a COG written and read back by
# raster-service, a season-logbook object written / found / fetched by scout-ingest's
# blob_store, the legacy TiTiler reading that COG through the gate with its own read-only
# account (write and scout bucket denied; no account ⇒ no S3 read), external plaintext
# refused, per-service bucket scoping, no secret in any output. And MinIO's network isolation
# (MINIO-COMMUNITY-EDITION-RECEIVES-NO-SECURITY-FIXES-01): sahool-minio only on the internal
# storage network and its loopback-publish network; a container on sahool-internal cannot resolve
# or reach it (with a control on the storage network); 127.0.0.1:9000/9001 still served;
# anonymous and wrong-secret requests refused. Isolation does not patch MinIO.
#
# Not covered (blocked by the freeze, reported not bypassed): the logbook HTTP endpoint
# reads and writes season_records, which exists only after migrations.
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

COMPOSE_FILE="$ROOT/docker-compose.v9.yml"
WORK="$(mktemp -d)"
ENV_FILE="$WORK/slice.env"
EVIDENCE="$WORK/evidence.log"
PROJECT="sahool-s3-slice-$(python3 -c 'import secrets; print(secrets.token_hex(4))')"
REPORT="${S3_TEST_REPORT:-$WORK/s3-compose-slice.json}"
TESTED_SHA="$(git -C "$ROOT" rev-parse HEAD)"

# Every ${VAR:?...} in the compose file gets a fresh random value so interpolation succeeds;
# only the slice's services ever start, and nothing here is a real secret.
python3 - "$COMPOSE_FILE" "$ENV_FILE" "$TESTED_SHA" <<'PY'
import re
import secrets
import sys

compose, out, sha = sys.argv[1], sys.argv[2], sys.argv[3]
names = sorted(set(re.findall(r"\$\{([A-Z0-9_]+):\?", open(compose, encoding="utf-8").read())))
values = {name: secrets.token_hex(16) for name in names}
values.update(
    TESTED_SHA=sha,
    SAHOOL_BUILD_ID=f"s3-slice-{sha[:12]}",
    MINIO_ROOT_USER="sahool-slice-root",
    RASTER_S3_ACCESS_KEY="sahool-slice-raster",
    SCOUT_INGEST_S3_ACCESS_KEY="sahool-slice-scout",
    # The legacy TiTiler's optional read-only account (TITILER-LEGACY-USES-SHARED-ADMIN-S3-KEY-01).
    TITILER_S3_ACCESS_KEY="sahool-slice-titiler",
    TITILER_S3_SECRET_KEY=secrets.token_hex(16),
)
with open(out, "w", encoding="utf-8") as fh:
    for name, value in sorted(values.items()):
        fh.write(f"{name}={value}\n")
PY
SECRETS=()
while IFS='=' read -r name value; do
  case "$name" in
    # Access keys are usernames that minio-init prints; only the secret halves count.
    *PASSWORD* | *SECRET* | *TOKEN*) SECRETS+=("$value") ;;
  esac
done <"$ENV_FILE"

dc() { docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }
cleanup() {
  dc --profile legacy-tiler down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT INT TERM
redact() {
  local text="$1" secret
  for secret in "${SECRETS[@]}"; do text="${text//"$secret"/[redacted]}"; done
  printf '%s\n' "$text"
}
fail() {
  echo "$1" >&2
  [[ -n "${2:-}" ]] && redact "$2" | tail -20 >&2
  exit 2
}
set_env() {
  python3 - "$ENV_FILE" "$1" "$2" <<'PY'
import sys

path, key, value = sys.argv[1:4]
lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if not ln.startswith(key + "=")]
if value:
    lines.append(f"{key}={value}")
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}

dc config --quiet
echo "compose config valid for the slice at ${TESTED_SHA}"

# 1) Storage exactly as production Compose provisions it.
dc up -d --wait --wait-timeout 120 sahool-minio
dc run --rm --no-deps sahool-minio-init >>"$EVIDENCE" 2>&1 || fail 'S3_SLICE_PROVISION_FAILED: sahool-minio-init did not finish' "$(cat "$EVIDENCE")"
grep -qx 'legacy TiTiler: read-only account on sahool-rasters' "$EVIDENCE" ||
  fail 'S3_SLICE_TITILER_ACCOUNT_NOT_PROVISIONED' "$(cat "$EVIDENCE")"
echo 'minio-init provisioned buckets and per-service users, including the read-only TiTiler account'

dc build -q sahool-raster-service sahool-scout-ingest >>"$EVIDENCE" 2>&1 || fail 'S3_SLICE_BUILD_FAILED' "$(tail -40 "$EVIDENCE")"

# 2) The approved compatibility break: no opt-in, raster-service refuses at startup.
set_env S3_ALLOW_PLAINTEXT_INTERNAL ""
dc up -d --no-deps sahool-raster-service >/dev/null
refused=""
for _ in $(seq 1 45); do
  logs="$(dc logs --no-color sahool-raster-service 2>&1 || true)"
  if grep -q "unsafe S3 endpoint configuration: plaintext_internal_requires_opt_in" <<<"$logs"; then
    refused=yes
    break
  fi
  sleep 2
done
printf '%s\n' "$logs" >>"$EVIDENCE"
[[ -n "$refused" ]] || fail 'S3_SLICE_BREAK_NOT_OBSERVED: raster-service did not refuse without the opt-in' "$logs"
dc rm -sf sahool-raster-service >/dev/null
echo 'without the opt-in raster-service refused at startup: plaintext_internal_requires_opt_in'

# 3) With the opt-in it starts, writes a COG and reads it back through GDAL in its own image.
set_env S3_ALLOW_PLAINTEXT_INTERNAL true
dc up -d --no-deps --wait --wait-timeout 180 sahool-raster-service >>"$EVIDENCE" 2>&1 ||
  fail 'S3_SLICE_RASTER_NOT_HEALTHY' "$(dc logs --no-color sahool-raster-service 2>&1 | tail -40)"
raster_out="$(dc exec -T sahool-raster-service python - <<'PY' 2>&1
import os
import tempfile

import numpy as np
import object_store
import rasterio
from rasterio.shutil import copy as rasterio_copy
from rasterio.transform import from_origin

assert os.environ["AWS_HTTPS"] == "NO" and os.environ["AWS_VIRTUAL_HOSTING"] == "FALSE"
assert os.environ["AWS_S3_ENDPOINT"] == "sahool-minio:9000"
pixels = (np.arange(128 * 128, dtype="uint16").reshape(128, 128) % 500)
with tempfile.TemporaryDirectory() as tmp:
    src, cog = f"{tmp}/s.tif", f"{tmp}/c.tif"
    profile = dict(driver="GTiff", width=128, height=128, count=1, dtype="uint16",
                   crs="EPSG:4326", transform=from_origin(44.0, 15.6, 0.001, 0.001))
    with rasterio.open(src, "w", **profile) as dst:
        dst.write(pixels, 1)
    rasterio_copy(src, cog, driver="COG")
    uri = object_store.upload_cog(cog, "fields/s3-slice/ndvi.tif")
assert uri == "s3://sahool-rasters/fields/s3-slice/ndvi.tif", uri
with rasterio.open(object_store.to_gdal_path(uri)) as ds:
    back = ds.read(1)
assert (back == pixels).all()
print("RASTER_COG", uri, int(back.min()), int(back.max()), int(back.size))
PY
)" || fail 'S3_SLICE_RASTER_COG_FAILED' "$raster_out"
printf '%s\n' "$raster_out" >>"$EVIDENCE"
grep -q '^RASTER_COG s3://sahool-rasters/fields/s3-slice/ndvi.tif 0 499 16384$' <<<"$raster_out" ||
  fail 'S3_SLICE_RASTER_COG_MISMATCH' "$raster_out"
echo 'raster-service wrote s3://sahool-rasters/fields/s3-slice/ndvi.tif and GDAL read it back pixel-exact'

# 4) scout-ingest's own image and env: season-logbook object written, found, fetched.
scout_out="$(dc run --rm -T --no-deps sahool-scout-ingest python - <<'PY' 2>&1
import urllib.request

from shared.security.season_logbook import derive_logbook_key
from shared.storage import blob_store

data = b"\xff\xd8\xff\xe0" + b"sahool-s3-slice-logbook" * 8 + b"\xff\xd9"
key = derive_logbook_key("tenant-slice", "00000000-0000-4000-8000-000000000001", "ab" * 32, "jpg")
ref = blob_store.upload_bytes(key, data, "image/jpeg")
assert ref.endswith(key) and "sahool-scout-ingest/sahool-scout-ingest" not in ref, ref
assert blob_store.object_exists(ref)
with urllib.request.urlopen(blob_store.presigned_get_url(ref, 60), timeout=10) as resp:
    assert resp.read() == data
print("SCOUT_LOGBOOK", key)
PY
)" || fail 'S3_SLICE_SCOUT_LOGBOOK_FAILED' "$scout_out"
printf '%s\n' "$scout_out" >>"$EVIDENCE"
grep -q '^SCOUT_LOGBOOK season-logbooks/tenant-slice/' <<<"$scout_out" || fail 'S3_SLICE_SCOUT_LOGBOOK_MISMATCH' "$scout_out"
echo 'scout-ingest blob_store wrote, found and fetched a season-logbooks/ object'

# 5) Per-service scoping from minio-init: the raster key cannot write the scout bucket.
scope_out="$(dc exec -T sahool-raster-service python - <<'PY' 2>&1
import os

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

client = boto3.client(
    "s3", endpoint_url="http://sahool-minio:9000",
    aws_access_key_id=os.environ["S3_ACCESS_KEY"], aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    region_name="us-east-1", config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
try:
    client.put_object(Bucket="sahool-scout-ingest", Key="season-logbooks/x/y/z.jpg", Body=b"x")
except ClientError as exc:
    print("SCOPE_DENIED", exc.response["Error"]["Code"])
else:
    print("SCOPE_ALLOWED")
PY
)" || true
printf '%s\n' "$scope_out" >>"$EVIDENCE"
grep -q '^SCOPE_DENIED AccessDenied$' <<<"$scope_out" || fail 'S3_SLICE_SCOPE_NOT_ENFORCED' "$scope_out"
echo 'raster service account denied on the scout bucket: AccessDenied'

# 5b) Network isolation (MINIO-COMMUNITY-EDITION-RECEIVES-NO-SECURITY-FIXES-01). It reduces who
# can reach MinIO; it does not patch MinIO. sahool-minio must sit on the internal storage network
# and its loopback-publish network only; a container on sahool-internal but not on the storage
# network must neither resolve sahool-minio nor connect to any of its addresses on :9000. The
# same probe, same image, on the storage network must reach it — otherwise a refusal proves nothing.
minio_cid="$(dc ps -q sahool-minio)"
raster_image="$(docker inspect --format '{{.Image}}' "$(dc ps -q sahool-raster-service)")"
STORAGE_NET="${PROJECT}_sahool-object-storage"
LOOPBACK_NET="${PROJECT}_sahool-object-storage-loopback"
INTERNAL_NET="${PROJECT}_sahool-internal"
minio_nets="$(docker inspect --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' "$minio_cid" | sed '/^$/d' | sort | paste -sd' ' -)"
[[ "$minio_nets" == "$STORAGE_NET $LOOPBACK_NET" ]] ||
  fail "S3_SLICE_STORAGE_NETWORK_NOT_ISOLATED: sahool-minio is attached to: ${minio_nets}"
[[ "$(docker network inspect --format '{{.Internal}}' "$STORAGE_NET")" == "true" ]] ||
  fail 'S3_SLICE_STORAGE_NETWORK_NOT_ISOLATED: the storage network is not internal'
[[ "$(docker network inspect --format '{{.Internal}}' "$INTERNAL_NET")" == "false" ]] ||
  fail 'S3_SLICE_STORAGE_NETWORK_PROBE_FAILED: sahool-internal missing or changed; the probe would prove nothing'
minio_ips="$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{"\n"}}{{end}}' "$minio_cid" | sed '/^$/d' | paste -sd' ' -)"
minio_storage_ip="$(docker inspect --format "{{(index .NetworkSettings.Networks \"$STORAGE_NET\").IPAddress}}" "$minio_cid")"
[[ -n "$minio_storage_ip" && "$(wc -w <<<"$minio_ips")" == 2 ]] ||
  fail "S3_SLICE_STORAGE_NETWORK_PROBE_FAILED: MinIO addresses not measurable (${minio_ips})"
isolation_probe='
import socket
import sys

try:
    socket.getaddrinfo("sahool-minio", 9000)
except socket.gaierror:
    print("ISOLATION resolve REFUSED")
else:
    print("ISOLATION resolve OPEN")
for ip in sys.argv[1:]:
    sock = socket.socket()
    sock.settimeout(3)
    try:
        sock.connect((ip, 9000))
    except OSError as exc:
        print("ISOLATION connect", ip, "REFUSED", type(exc).__name__)
    else:
        print("ISOLATION connect", ip, "OPEN")
    finally:
        sock.close()
'
# shellcheck disable=SC2086 # one argument per MinIO address
isolated="$(docker run --rm --pull never --network "$INTERNAL_NET" --entrypoint "" "$raster_image" python -c "$isolation_probe" $minio_ips 2>&1)" ||
  fail 'S3_SLICE_STORAGE_NETWORK_PROBE_FAILED: probe container on sahool-internal did not run' "$isolated"
printf '%s\n' "$isolated" >>"$EVIDENCE"
[[ "$(grep -c '^ISOLATION .* REFUSED' <<<"$isolated")" == 3 ]] && ! grep -q ' OPEN$' <<<"$isolated" ||
  fail 'S3_SLICE_STORAGE_NETWORK_NOT_ISOLATED: a container on sahool-internal reached sahool-minio' "$isolated"
control="$(docker run --rm --pull never --network "$STORAGE_NET" --entrypoint "" "$raster_image" python -c "$isolation_probe" "$minio_storage_ip" 2>&1)" ||
  fail 'S3_SLICE_STORAGE_NETWORK_CONTROL_FAILED: probe container on the storage network did not run' "$control"
printf '%s\n' "$control" >>"$EVIDENCE"
[[ "$control" == "ISOLATION resolve OPEN
ISOLATION connect ${minio_storage_ip} OPEN" ]] ||
  fail 'S3_SLICE_STORAGE_NETWORK_CONTROL_FAILED: the same probe on the storage network did not reach MinIO' "$control"
echo "sahool-minio only on the internal storage network and its loopback network; from sahool-internal: name unresolved, ${minio_ips// /, } :9000 unreachable; the same probe on the storage network reaches it"

# 5c) Unauthorized access refused, and the loopback API/console still published on the host:
# anonymous requests (no signature) and a wrong secret get no object and no listing.
loopback_out="$(python3 - <<'PY' 2>&1
import urllib.error
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def status(url):
    try:
        with opener.open(url, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


print("LOOPBACK api", status("http://127.0.0.1:9000/minio/health/live"))
print("LOOPBACK console", status("http://127.0.0.1:9001/"))
for path in (
    "/sahool-rasters/fields/s3-slice/ndvi.tif",
    "/sahool-rasters?list-type=2",
    "/sahool-scout-ingest?list-type=2",
    "/",
):
    print("ANONYMOUS", path, status("http://127.0.0.1:9000" + path))
PY
)" || fail 'S3_SLICE_LOOPBACK_PORT_UNAVAILABLE: host-side probe failed' "$loopback_out"
printf '%s\n' "$loopback_out" >>"$EVIDENCE"
grep -qx 'LOOPBACK api 200' <<<"$loopback_out" && grep -qx 'LOOPBACK console 200' <<<"$loopback_out" ||
  fail 'S3_SLICE_LOOPBACK_PORT_UNAVAILABLE: 127.0.0.1:9000/9001 not served after isolation' "$loopback_out"
[[ "$(grep -c '^ANONYMOUS .* 403$' <<<"$loopback_out")" == 4 ]] ||
  fail 'S3_SLICE_ANONYMOUS_ACCESS_NOT_REFUSED' "$loopback_out"
wrong_secret="$(dc exec -T sahool-raster-service python - <<'PY' 2>&1
import os

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

client = boto3.client(
    "s3", endpoint_url="http://sahool-minio:9000",
    aws_access_key_id=os.environ["S3_ACCESS_KEY"], aws_secret_access_key="not-the-secret-" + "0" * 24,
    region_name="us-east-1", config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
try:
    client.get_object(Bucket="sahool-rasters", Key="fields/s3-slice/ndvi.tif")["Body"].read()
except ClientError as exc:
    print("WRONG_SECRET DENIED", exc.response["Error"]["Code"])
else:
    print("WRONG_SECRET ALLOWED")
PY
)" || true
printf '%s\n' "$wrong_secret" >>"$EVIDENCE"
grep -qx 'WRONG_SECRET DENIED SignatureDoesNotMatch' <<<"$wrong_secret" ||
  fail 'S3_SLICE_WRONG_SECRET_NOT_REFUSED' "$wrong_secret"
echo 'loopback API 200 and console 200 on 127.0.0.1; anonymous object/list requests 403; wrong secret SignatureDoesNotMatch'

# 6) Legacy TiTiler (profile) reads the COG through the gate; without the opt-in it exits 78.
dc --profile legacy-tiler up -d --no-deps --wait --wait-timeout 120 sahool-titiler >>"$EVIDENCE" 2>&1 ||
  fail 'S3_SLICE_TITILER_NOT_HEALTHY' "$(dc --profile legacy-tiler logs --no-color sahool-titiler 2>&1 | tail -30)"
titiler_out="$(dc --profile legacy-tiler exec -T sahool-titiler python -c "import json, urllib.request; d = json.load(urllib.request.urlopen('http://localhost:8000/cog/info?url=s3://sahool-rasters/fields/s3-slice/ndvi.tif', timeout=20)); print('TITILER_INFO', d['width'], d['height'], d['dtype'])" 2>&1)" ||
  fail 'S3_SLICE_TITILER_READ_FAILED' "$titiler_out"
printf '%s\n' "$titiler_out" >>"$EVIDENCE"
grep -q '^TITILER_INFO 128 128 uint16$' <<<"$titiler_out" || fail 'S3_SLICE_TITILER_MISMATCH' "$titiler_out"
dc --profile legacy-tiler rm -sf sahool-titiler >/dev/null
echo 'legacy TiTiler read the COG over /vsis3/ through the gate with its read-only account'

# 6b) The TiTiler account itself, outside TiTiler: read allowed, every write and the scout bucket
# denied. The key pair reaches the container by name only (-e NAME), never on a command line.
SLICE_TITILER_ACCESS_KEY="$(sed -n 's/^TITILER_S3_ACCESS_KEY=//p' "$ENV_FILE")"
SLICE_TITILER_SECRET_KEY="$(sed -n 's/^TITILER_S3_SECRET_KEY=//p' "$ENV_FILE")"
export SLICE_TITILER_ACCESS_KEY SLICE_TITILER_SECRET_KEY
titiler_scope="$(dc run --rm -T --no-deps -e SLICE_TITILER_ACCESS_KEY -e SLICE_TITILER_SECRET_KEY sahool-raster-service python - <<'PY' 2>&1
import os

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

client = boto3.client(
    "s3", endpoint_url="http://sahool-minio:9000",
    aws_access_key_id=os.environ["SLICE_TITILER_ACCESS_KEY"],
    aws_secret_access_key=os.environ["SLICE_TITILER_SECRET_KEY"],
    region_name="us-east-1", config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
COG = "fields/s3-slice/ndvi.tif"


def attempt(label, call):
    try:
        call()
    except ClientError as exc:
        print("TITILER_KEY", label, "DENIED", exc.response["Error"]["Code"])
    else:
        print("TITILER_KEY", label, "ALLOWED")


attempt("list_rasters", lambda: client.list_objects_v2(Bucket="sahool-rasters", Prefix="fields/"))
attempt("get_rasters", lambda: client.get_object(Bucket="sahool-rasters", Key=COG)["Body"].read())
attempt("put_rasters", lambda: client.put_object(Bucket="sahool-rasters", Key="fields/x/w.tif", Body=b"x"))
attempt("overwrite_cog", lambda: client.put_object(Bucket="sahool-rasters", Key=COG, Body=b"x"))
attempt("delete_cog", lambda: client.delete_object(Bucket="sahool-rasters", Key=COG))
attempt("list_scout", lambda: client.list_objects_v2(Bucket="sahool-scout-ingest"))
attempt("put_scout", lambda: client.put_object(Bucket="sahool-scout-ingest", Key="season-logbooks/x/y/z.jpg", Body=b"x"))
attempt("create_bucket", lambda: client.create_bucket(Bucket="sahool-slice-titiler-probe"))
PY
)" || true
unset SLICE_TITILER_ACCESS_KEY SLICE_TITILER_SECRET_KEY
printf '%s\n' "$titiler_scope" >>"$EVIDENCE"
expected_scope='TITILER_KEY list_rasters ALLOWED
TITILER_KEY get_rasters ALLOWED
TITILER_KEY put_rasters DENIED AccessDenied
TITILER_KEY overwrite_cog DENIED AccessDenied
TITILER_KEY delete_cog DENIED AccessDenied
TITILER_KEY list_scout DENIED AccessDenied
TITILER_KEY put_scout DENIED AccessDenied
TITILER_KEY create_bucket DENIED AccessDenied'
[[ "$(grep '^TITILER_KEY ' <<<"$titiler_scope")" == "$expected_scope" ]] ||
  fail 'S3_SLICE_TITILER_KEY_NOT_READ_ONLY' "$titiler_scope"
echo 'TiTiler account: list and get on sahool-rasters allowed; put, overwrite, delete, scout bucket and bucket creation AccessDenied'

# 6c) Without the account (both halves empty, the template default) TiTiler gets no S3 read.
set_env TITILER_S3_ACCESS_KEY ""
set_env TITILER_S3_SECRET_KEY ""
dc --profile legacy-tiler up -d --no-deps --wait --wait-timeout 120 sahool-titiler >>"$EVIDENCE" 2>&1 ||
  fail 'S3_SLICE_TITILER_NOT_HEALTHY' "$(dc --profile legacy-tiler logs --no-color sahool-titiler 2>&1 | tail -30)"
no_account="$(dc --profile legacy-tiler exec -T sahool-titiler python - <<'PY' 2>&1
import os
import urllib.error
import urllib.request

assert not os.environ.get("AWS_ACCESS_KEY_ID") and not os.environ.get("AWS_SECRET_ACCESS_KEY")
url = "http://localhost:8000/cog/info?url=s3://sahool-rasters/fields/s3-slice/ndvi.tif"
try:
    urllib.request.urlopen(url, timeout=60)
except urllib.error.HTTPError as exc:
    print("TITILER_NO_ACCOUNT", "REFUSED", exc.code)
else:
    print("TITILER_NO_ACCOUNT", "READ")
PY
)" || fail 'S3_SLICE_TITILER_NO_ACCOUNT_PROBE_FAILED' "$no_account"
printf '%s\n' "$no_account" >>"$EVIDENCE"
grep -Eq '^TITILER_NO_ACCOUNT REFUSED [45][0-9][0-9]$' <<<"$no_account" ||
  fail 'S3_SLICE_TITILER_READ_WITHOUT_ACCOUNT' "$no_account"
dc --profile legacy-tiler rm -sf sahool-titiler >/dev/null
echo "legacy TiTiler without an account: no S3 read ($(cut -d' ' -f2- <<<"$no_account"))"

set +e
titiler_refusal="$(dc --profile legacy-tiler run --rm -T --no-deps -e S3_ALLOW_PLAINTEXT_INTERNAL=false sahool-titiler 2>&1)"
status=$?
set -e
printf '%s\n' "$titiler_refusal" >>"$EVIDENCE"
[[ "$status" == "78" ]] && grep -qx 'unsafe S3 endpoint configuration: plaintext_internal_requires_opt_in' <<<"$titiler_refusal" ||
  fail "S3_SLICE_TITILER_REFUSAL_FAILED: status=${status}" "$titiler_refusal"
echo 'legacy TiTiler without the opt-in: exit 78 before uvicorn'

# 7) External plaintext is refused by both adapters even with the opt-in.
external_out="$(dc run --rm -T --no-deps -e S3_ENDPOINT=http://objects.example.test sahool-scout-ingest python - <<'PY' 2>&1
from shared.storage import blob_store

try:
    blob_store.upload_bytes("season-logbooks/t/s/a.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")
except Exception as exc:  # noqa: BLE001 - the code is what is asserted
    print("SCOUT_EXTERNAL", type(exc).__name__, str(exc))
else:
    print("SCOUT_EXTERNAL_ACCEPTED")
PY
)" || true
printf '%s\n' "$external_out" >>"$EVIDENCE"
grep -q '^SCOUT_EXTERNAL .*plaintext_external_forbidden' <<<"$external_out" || fail 'S3_SLICE_SCOUT_EXTERNAL_NOT_REFUSED' "$external_out"
grep -qF 'objects.example.test' <<<"$external_out" && fail 'S3_SLICE_REFUSAL_ECHOED_INPUT' "$external_out"
set +e
raster_external="$(dc run --rm -T --no-deps -e S3_ENDPOINT=http://objects.example.test sahool-raster-service python -c "import object_store" 2>&1)"
status=$?
set -e
printf '%s\n' "$raster_external" >>"$EVIDENCE"
[[ "$status" != "0" ]] && grep -q 'unsafe S3 endpoint configuration: plaintext_external_forbidden' <<<"$raster_external" ||
  fail "S3_SLICE_RASTER_EXTERNAL_NOT_REFUSED: status=${status}" "$raster_external"
echo 'external plaintext refused by scout-ingest and raster-service, input not echoed'

# 8) No generated secret in any output or container log; grep -q never prints a match.
dc --profile legacy-tiler logs --no-color >>"$EVIDENCE" 2>&1 || true
for secret in "${SECRETS[@]}"; do
  if grep -qF -- "$secret" "$EVIDENCE"; then
    echo 'S3_SLICE_SECRET_IN_EVIDENCE: a generated secret appears in the collected output' >&2
    exit 2
  fi
done
echo 'no generated secret in outputs or container logs'

python3 - "$REPORT" "$TESTED_SHA" <<'PY'
import json
import sys

report, sha = sys.argv[1], sys.argv[2]
json.dump(
    {
        "schema": "sahool.s3_compose_slice_acceptance.v1",
        "tested_sha": sha,
        "compose_file": "docker-compose.v9.yml",
        "services": ["sahool-minio", "sahool-minio-init", "sahool-raster-service",
                     "sahool-scout-ingest", "sahool-titiler (legacy-tiler)"],
        "database": "none (no postgres, no migrator, no migration)",
        "results": {
            "break_without_opt_in": "plaintext_internal_requires_opt_in at startup",
            "raster_cog": "s3://sahool-rasters/fields/s3-slice/ndvi.tif written and read pixel-exact",
            "scout_logbook_object": "season-logbooks/ written, found, fetched by presigned URL",
            "service_scoping": "raster key AccessDenied on scout bucket",
            "storage_network_isolation": "sahool-minio only on sahool-object-storage (internal) "
            "and sahool-object-storage-loopback; from sahool-internal: name unresolved, every "
            "MinIO address unreachable on :9000; control on the storage network reaches it",
            "unauthorized_access": "anonymous object/list/bucket-list 403; wrong secret "
            "SignatureDoesNotMatch; 127.0.0.1:9000 health 200 and :9001 console 200",
            "legacy_titiler": "cog/info 128x128 uint16; without opt-in exit 78",
            "legacy_titiler_account": "read-only on sahool-rasters: list/get allowed; put, "
            "overwrite, delete, scout bucket, bucket creation AccessDenied; no account => no S3 read",
            "external_plaintext": "refused by scout-ingest and raster-service, input not echoed",
            "secrets_in_output": "none",
        },
        "not_covered": "logbook HTTP endpoint (needs season_records, i.e. migrations; frozen)",
        "verdict": "PASS",
    },
    open(report, "w", encoding="utf-8"),
    indent=2,
)
PY
echo "S3 compose slice acceptance PASS at ${TESTED_SHA}"
