# SAHOOL — Docker Compose / `.env` Contract Audit & Fix

Date: 2026-07-06
Input ZIP: `sahool_main_fe9caca_minio_s3_storage_sync_fixed.zip`
Output ZIP: `sahool_main_fe9caca_compose_env_contract_fixed.zip`

## Scope

Audited every compose file present in the repository against the env examples:

- `.env.example`
- `frontend/.env.example`
- `docker-compose.v9.yml`
- `docker-compose.fixed.yml`
- `docker-compose.unified.yml`
- `docker-compose.light.yml`
- `docker-compose.erpnext.yml`
- `docker-compose.rag-kg-mcp.yml`
- `docker-compose.test.yml`
- `docker-compose.v9.gpu.yml`
- `docker-compose.odoo-snippet.yml`
- `frontend/docker-compose.web.yml`

## Findings before fix

1. Compose referenced more than 100 variables that were not declared in env examples.
2. `docker-compose.fixed.yml` still hardcoded `MINIO_ROOT_USER: sahool-admin`, while v9 had already been fixed.
3. S3/MinIO credential interpolation used nested expressions in several raster/TiTiler services. This is risky because Compose interpolation semantics are easy to misread and can drift by implementation.
4. `docker-compose.fixed.yml` had no explicit S3/MinIO storage contract for `sahool-raster-service`.
5. No CI gate existed to prove, for every compose service, that referenced variables are declared and credential aliases stay consistent.

## Fixes applied

### 1. Centralized all compose-referenced variables

Added a `Compose contract defaults` section to `.env.example` covering all variables referenced by compose files and not already declared.

Result:

- compose variable references checked: `165`
- env keys checked: `186`
- missing compose variable declarations: `0`
- duplicate keys in env examples: `0`

### 2. Fixed `docker-compose.fixed.yml` MinIO drift

Changed:

```yaml
MINIO_ROOT_USER: sahool-admin
```

To:

```yaml
MINIO_ROOT_USER: ${MINIO_ROOT_USER:-sahool-admin}
```

### 3. Standardized raster S3/MinIO contract

Added explicit S3 storage env vars to `docker-compose.fixed.yml:sahool-raster-service`:

```yaml
S3_ENDPOINT
S3_BUCKET
S3_ACCESS_KEY
S3_SECRET_KEY
S3_REGION
S3_USE_SSL
S3_ALLOW_FILE_FALLBACK
```

### 4. Removed risky nested S3 interpolation in v9

Changed raster/TiTiler credential values to direct contract vars:

```yaml
S3_ACCESS_KEY: ${S3_ACCESS_KEY:-sahool-admin}
S3_SECRET_KEY: ${S3_SECRET_KEY:?S3_SECRET_KEY required}
AWS_ACCESS_KEY_ID: ${S3_ACCESS_KEY:-sahool-admin}
AWS_SECRET_ACCESS_KEY: ${S3_SECRET_KEY:?S3_SECRET_KEY required}
```

The env example keeps local/dev aliases aligned:

```env
MINIO_ROOT_USER=sahool-admin
MINIO_ACCESS_KEY=sahool-admin
S3_ACCESS_KEY=sahool-admin
MINIO_ROOT_PASSWORD=minio_pass_change_me
MINIO_SECRET_KEY=minio_pass_change_me
S3_SECRET_KEY=minio_pass_change_me
```

### 5. Added CI gate

New file:

```text
scripts/ci/compose_env_contract_gate.py
```

It fails CI if:

- a compose `${VAR}` is not declared in `.env.example` or `frontend/.env.example`
- an env example contains duplicate keys
- MinIO/S3 aliases drift
- `sahool-minio` hardcodes `MINIO_ROOT_USER`
- raster services miss required storage env variables
- TiTiler misses required S3 env variables
- nested S3/MinIO credential interpolation returns

### 6. Wired the gate into CI

Updated:

```text
.github/workflows/ci.yml
```

Added step:

```yaml
- name: compose-env-contract-gate
  run: python scripts/ci/compose_env_contract_gate.py
```

### 7. Added per-service matrix

Generated:

```text
COMPOSE_ENV_SERVICE_MATRIX_20260706.csv
```

This file lists, for every compose service:

- compose file
- service name
- number of env keys
- interpolated env references
- missing references, now empty

## Validation run

Executed successfully:

```bash
python3 -m py_compile scripts/ci/compose_env_contract_gate.py scripts/ci/minio_s3_contract_gate.py
python3 scripts/ci/compose_env_contract_gate.py
python3 scripts/ci/minio_s3_contract_gate.py
python3 scripts/ci/service_port_gate.py
python3 scripts/ci/nginx_compose_dns_gate.py
python3 -c "import yaml; yaml.safe_load(open('docker-compose.v9.yml')); yaml.safe_load(open('docker-compose.fixed.yml')); yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Results:

```text
service-port-gate: PASS
nginx-compose-dns-gate: PASS (15 upstreams)
MinIO/S3 credential and storage contract is consistent
compose-env contract: OK
checked 10 compose files, 186 env keys, 165 compose references
YAML OK docker-compose.v9.yml
YAML OK docker-compose.fixed.yml
YAML OK .github/workflows/ci.yml
```

## Remaining note

This patch validates static compose/env consistency. A final runtime check should still be run on the target machine with Docker available:

```bash
docker compose -f docker-compose.v9.yml config
docker compose -f docker-compose.v9.yml up -d --force-recreate sahool-minio sahool-raster-service sahool-raster-backfill-scan-worker sahool-titiler
python scripts/runtime/env_doctor.py
```
