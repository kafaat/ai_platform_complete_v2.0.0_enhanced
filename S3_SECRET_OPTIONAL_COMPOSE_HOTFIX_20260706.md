# S3_SECRET_KEY Optional Compose Interpolation Hotfix — 2026-07-06

## Root cause

`docker compose build` failed before image build because several services used required interpolation:

```yaml
S3_SECRET_KEY: ${S3_SECRET_KEY:?S3_SECRET_KEY required}
AWS_SECRET_ACCESS_KEY: ${S3_SECRET_KEY:?S3_SECRET_KEY required}
```

S3/MinIO object storage is optional when `S3_BUCKET` is empty, so Compose must not require `S3_SECRET_KEY` at interpolation time for local/dev builds.

## Fix applied

Changed required interpolation to optional empty fallback in:

- `docker-compose.v9.yml`
- `docker-compose.fixed.yml`

New form:

```yaml
S3_SECRET_KEY: ${S3_SECRET_KEY:-}
AWS_SECRET_ACCESS_KEY: ${S3_SECRET_KEY:-}
```

## Runtime safety preserved

`services/raster-service/object_store.py` now fails closed at runtime if S3 is actually enabled but credentials are missing:

```text
S3_BUCKET/S3_ENDPOINT are configured but S3_ACCESS_KEY/S3_SECRET_KEY are missing; set S3_SECRET_KEY in .env or leave S3_BUCKET empty for local file:// storage
```

So local builds no longer fail, while real S3 usage still cannot silently degrade with missing credentials.

## CI hardening

Updated `scripts/ci/minio_s3_contract_gate.py` to reject future reintroduction of required Compose interpolation for `S3_SECRET_KEY`.

## Verification run

```text
✓ MinIO/S3 credential and storage contract is consistent
compose-env contract: OK
backfill-ui-sync contract: OK
service-port-gate: PASS
nginx-compose-dns-gate: PASS (15 upstreams)
YAML OK docker-compose.v9.yml
YAML OK docker-compose.fixed.yml
YAML OK .github/workflows/ci.yml
```

## Local command to retry

```powershell
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu build --no-cache
```

If you want MinIO/S3 persistence rather than local `file:///data/rasters`, set in your `.env`:

```env
S3_BUCKET=sahool-rasters
S3_ACCESS_KEY=<same as MINIO_ROOT_USER or service account>
S3_SECRET_KEY=<same as MINIO_ROOT_PASSWORD or service account secret>
```

If `S3_BUCKET` stays empty, the raster service keeps local COG storage under `/data/rasters`.
