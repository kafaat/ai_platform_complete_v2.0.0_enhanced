# SAHOOL MinIO/S3 Storage Sync Fix Report — 2026-07-06

## Scope
Fixed the credential/source-of-truth mismatch between `.env.example`, `docker-compose.v9.yml`, raster COG persistence, the async backfill worker, and TiTiler diagnostics.

## Root cause
`docker-compose.v9.yml` hardcoded `MINIO_ROOT_USER: sahool-admin` while `.env.example` advertised `MINIO_ROOT_USER=sahool`. Network and MinIO health checks could still pass, but backend services using `.env`-derived `MINIO_ACCESS_KEY`/`S3_ACCESS_KEY` could fail authentication against the running MinIO container.

## Changes applied

### 1. docker-compose.v9.yml
- Replaced the hardcoded MinIO root user with an interpolated source of truth:
  - `MINIO_ROOT_USER: ${MINIO_ROOT_USER:-sahool-admin}`
- Added an explicit S3/MinIO environment contract to:
  - `sahool-raster-service`
  - `sahool-raster-cache-invalidation-worker`
  - `sahool-raster-backfill-scan-worker`
- Added S3/GDAL environment variables to `sahool-titiler`.
- Mounted `raster-data` read-only into `sahool-titiler` so local `file:///data/rasters` COG diagnostics can work in development.

### 2. .env.example
- Aligned default MinIO credentials:
  - `MINIO_ROOT_USER=sahool-admin`
  - `MINIO_ACCESS_KEY=sahool-admin`
  - `S3_ACCESS_KEY=sahool-admin`
- Added the full S3 contract:
  - `S3_ENDPOINT`
  - `S3_ENDPOINT_HOST`
  - `S3_BUCKET`
  - `S3_ACCESS_KEY`
  - `S3_SECRET_KEY`
  - `S3_REGION`
  - `S3_USE_SSL`
  - `S3_ALLOW_FILE_FALLBACK`

### 3. frontend/run_all.sh and frontend/run_all.ps1
- Updated local bootstrap defaults from `MINIO_ROOT_USER=sahool` to `MINIO_ROOT_USER=sahool-admin`.

### 4. CI guard
Added:

```text
scripts/ci/minio_s3_contract_gate.py
```

This gate fails if:
- `docker-compose.v9.yml` hardcodes `MINIO_ROOT_USER` instead of interpolating it.
- `.env.example` lacks the S3 contract keys.
- `MINIO_ACCESS_KEY` or `S3_ACCESS_KEY` drift away from the default MinIO root credential without a dedicated documented account.
- `sahool-titiler` does not have both local raster volume diagnostics and S3 endpoint variables.

The gate is wired into `.github/workflows/ci.yml` under `structural-lint`.

### 5. Runtime doctor
Updated `scripts/runtime/env_doctor.py` to include the new MinIO/S3 CI gate in required files and to surface MinIO/S3 credential drift in its environment check.

## Validation performed

```text
python3 -m py_compile scripts/ci/minio_s3_contract_gate.py scripts/runtime/env_doctor.py
python3 scripts/ci/minio_s3_contract_gate.py
python3 scripts/runtime/env_doctor.py --root . --mode preflight --format text
python3 -c "import yaml; yaml.safe_load(open('docker-compose.v9.yml')); yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Observed results:
- YAML parse: pass.
- New MinIO/S3 CI gate: pass.
- Runtime doctor: no failures; expected warnings only for missing local secrets and occupied host ports in this execution environment.

## Operational note
Local/dev can still leave `S3_BUCKET=` empty. In that mode COGs remain stored as:

```text
file:///data/rasters/...
```

For production/shared storage, set:

```env
S3_BUCKET=sahool-rasters
S3_ENDPOINT=http://sahool-minio:9000
S3_ACCESS_KEY=<minio-or-service-account-access-key>
S3_SECRET_KEY=<matching-secret>
```

Then recreate the affected services:

```bash
docker compose -f docker-compose.v9.yml up -d --force-recreate sahool-minio sahool-raster-service sahool-raster-backfill-scan-worker sahool-raster-cache-invalidation-worker sahool-titiler
```
