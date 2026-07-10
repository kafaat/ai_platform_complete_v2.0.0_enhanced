# Docker Build Checklist — Critical + Extended Sahool Services

Date: 2026-07-10  
Scope: Docker build, container startup, health/readiness, security scan, and evidence generation for the production-certification path.

> **مصدر الحقيقة القابل للتنفيذ = `scripts/ci/docker_build_matrix_verifier.py`.** بعض
> كتل الأوامر أدناه تحمل منافذ/رايات من المسوّدة الأصليّة صُحِّحت في السكربت بعد تحقّق
> ميدانيّ — عند أيّ تعارض، السكربت هو المرجع. تصحيحات جوهريّة:
> - **edge-inference** منفذ الحاوية الفعليّ **8100** (لا 8180)؛ الـDockerfile الوحيد
>   `Dockerfile.arm64` (قاعدة python:3.12 متعدّدة المعماريّات). · **sam2-inference** **8080**.
> - رايات fail-closed الحقيقيّة الموجودة في الكود: `EDGE_PRODUCTION_REQUIRED` ·
>   `EDGE_READINESS_MODE` (edge)؛ و`SAM2_CHECKPOINT` + `SAM2_MODEL_CFG` (sam2).
>   الرايات `RASTER_RUNTIME_MODE` · `WEATHER_CACHE_BACKEND` · `EDGE_MODEL_DIR` ·
>   `SAM2_PRODUCTION_REQUIRED` · `SAM2_READINESS_MODE` · `SAM2_MODEL_DIR` **غير مقروءة**
>   في الكود اليوم (خاملة إن مُرِّرت — الحاويات تتجاهل env المجهول).

This checklist extends the four critical services:

- `raster-service`
- `weather-service`
- `edge-inference`
- `sam2-inference`

with these additional release-sensitive services:

- `auth`
- `sahool-platform`
- `odoo-bridge`

The checklist is intentionally evidence-driven. A service is not considered production-certified because a Dockerfile exists; it must build, start, expose honest `/healthz` and `/readyz`, and produce CI evidence.

---

## 1. Global pre-build checks

Run before any image build:

```bash
python scripts/ci/pip_audit_resolution_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/test_requirements_inventory_guard.py --check
python scripts/ci/route_mount_contract_guard.py --check
python scripts/ci/api_versioning_policy_guard.py --check
python scripts/ci/health_readiness_schema_guard.py
python scripts/ci/contract_capabilities_schema_guard.py --check
```

Raster-specific pre-build guards:

```bash
python scripts/ci/raw_data_processing_contract_guard.py
python scripts/ci/raster_pixel_qa_indicator_guard.py
python scripts/ci/raster_validated_product_guard.py
python scripts/ci/raster_topographic_qa_guard.py
```

Weather-specific pre-build guard:

```bash
python scripts/ci/raw_weather_processing_contract_guard.py
```

Container/model guards:

```bash
python scripts/ci/container_fleet_contract_guard.py
python scripts/ci/ai_container_contract_guard.py
python scripts/ci/runtime_container_deep_contract_guard.py
python scripts/ci/edge_model_contract_guard.py
python scripts/ci/edge_production_readiness_guard.py
```

Fail immediately if any guard fails.

---

## 2. Critical service build commands

### 2.1 raster-service

```bash
docker build \
  -f services/raster-service/Dockerfile \
  -t sahool/raster-service:ci \
  .
```

Required in image:

```bash
docker run --rm --entrypoint sh sahool/raster-service:ci -c '
  test -f /app/main.py &&
  test -f /app/raw_data_processing.py &&
  test -f /app/raster_pixel_processing.py &&
  test -f /app/raster_cloud_mask_strategies.py &&
  test -f /app/raster_validated_product.py &&
  test -f /app/raster_topographic_qa.py
'
```

Import smoke:

```bash
docker run --rm --entrypoint python sahool/raster-service:ci - <<'PY'
import raw_data_processing
import raster_pixel_processing
import raster_cloud_mask_strategies
import raster_validated_product
import raster_topographic_qa
print("raster imports ok")
PY
```

Runtime smoke:

```bash
docker run --rm -d \
  --name sahool-raster-ci \
  -p 18001:8001 \
  -e RASTER_RUNTIME_MODE=ci \
  -e FIELD_DEM_PATH= \
  sahool/raster-service:ci

curl -fsS http://localhost:18001/healthz
curl -sS http://localhost:18001/readyz || true
docker logs sahool-raster-ci --tail=100
docker stop sahool-raster-ci
```

Pass criteria:

- `/healthz` returns 200.
- `/readyz` is honest; degraded is allowed when DEM/CDSE/DB dependencies are absent.
- Logs contain no `ModuleNotFoundError`, `ImportError`, or startup `Traceback`.
- Indicator responses contain `validated_raster_product`, `pixel_qa`, `quality_flags`, and `provenance`.

Certification smoke still required later:

- Sentinel-2 L2A COG fixture.
- SCL/CLM/CLP or explicit cloud strategy.
- DEM fixture.
- `sun_azimuth_deg` + `sun_altitude_deg`.
- Field polygon fixture.

---

### 2.2 weather-service

```bash
docker build \
  -f services/weather-service/Dockerfile \
  -t sahool/weather-service:ci \
  .
```

Required in image:

```bash
docker run --rm --entrypoint sh sahool/weather-service:ci -c '
  test -f /app/main.py &&
  test -f /app/weather_runtime.py &&
  test -f /app/raw_weather_processing.py &&
  test -f /app/open_meteo.py &&
  test -f /app/cache.py
'
```

Runtime smoke:

```bash
docker run --rm -d \
  --name sahool-weather-ci \
  -p 18092:8000 \
  -e WEATHER_REDIS_URL= \
  -e WEATHER_CACHE_BACKEND=memory \
  sahool/weather-service:ci

curl -fsS http://localhost:18092/healthz
curl -sS http://localhost:18092/readyz || true
docker logs sahool-weather-ci --tail=100
docker stop sahool-weather-ci
```

Raw weather smoke:

```bash
curl -fsS -X POST http://localhost:18092/v1/weather/raw/process \
  -H 'Content-Type: application/json' \
  -H "X-Service-Token: ${SERVICE_TOKEN}" \
  -d '{
    "source_kind": "forecast",
    "provider": "open-meteo",
    "model": "open-meteo-global",
    "location": {"lat": 16.164, "lon": 44.776},
    "raw_payload": {
      "hourly": {
        "time": ["2026-07-10T10:00:00Z"],
        "temperature_2m": [32.5],
        "relative_humidity_2m": [41],
        "wind_speed_10m": [4.2]
      }
    },
    "include_raw_payload": false,
    "max_items": 1000
  }'
```

Pass criteria:

- `raw_data_processing = true`.
- `fabricated_weather = false`.
- `operation_window_computed = false`.
- `numeric_summary`, `provenance`, and `source_kind` are present.

Redis live smoke for P-CERT-3:

```bash
docker run -d --rm --name sahool-redis-ci -p 16379:6379 redis:7-alpine
WEATHER_REDIS_INTEGRATION_URL=redis://localhost:16379/0 \
  pytest -q services/weather-service/tests/test_weather_redis_live_optional.py
docker stop sahool-redis-ci
```

---

### 2.3 edge-inference

Current Dockerfile path is:

```text
services/edge-inference/Dockerfile.arm64
```

Build:

```bash
docker build \
  -f services/edge-inference/Dockerfile.arm64 \
  -t sahool/edge-inference:ci \
  .
```

Required in image:

```bash
docker run --rm --entrypoint sh sahool/edge-inference:ci -c '
  test -f /app/main.py &&
  test -f /app/models_manifest/edge_models.required.json
'
```

Fail-closed runtime smoke without models:

```bash
docker run --rm -d \
  --name sahool-edge-ci \
  -p 18180:8180 \
  -e EDGE_PRODUCTION_REQUIRED=true \
  -e EDGE_READINESS_MODE=strict \
  -e EDGE_MODEL_DIR=/models \
  sahool/edge-inference:ci

curl -fsS http://localhost:18180/healthz
curl -sS http://localhost:18180/readyz || true
curl -sS http://localhost:18180/capabilities || true
docker logs sahool-edge-ci --tail=100
docker stop sahool-edge-ci
```

Expected without models:

- `/healthz` returns 200.
- `/readyz` is not ready or reports missing models.
- No fake inference path is enabled.

P-CERT-4 model-present smoke:

```bash
docker run --rm -d \
  --name sahool-edge-ci-model \
  -p 18181:8180 \
  -v "$PWD/artifacts/edge-models:/models:ro" \
  -e EDGE_PRODUCTION_REQUIRED=true \
  -e EDGE_READINESS_MODE=strict \
  -e EDGE_MODEL_DIR=/models \
  sahool/edge-inference:ci

curl -fsS http://localhost:18181/readyz
curl -fsS http://localhost:18181/capabilities
docker stop sahool-edge-ci-model
```

Pass criteria:

- Required ONNX models are discovered.
- `ready = true` only when artifacts exist.
- Response identifies model version/provenance.

---

### 2.4 sam2-inference

```bash
docker build \
  -f services/sam2-inference/Dockerfile \
  -t sahool/sam2-inference:ci \
  .
```

Required in image:

```bash
docker run --rm --entrypoint sh sahool/sam2-inference:ci -c '
  test -f /app/main.py &&
  test -f /app/sam2_runtime.py
'
```

Fail-closed runtime smoke without artifacts:

```bash
docker run --rm -d \
  --name sahool-sam2-ci \
  -p 18150:8080 \
  -e SAM2_PRODUCTION_REQUIRED=true \
  -e SAM2_READINESS_MODE=strict \
  -e SAM2_MODEL_DIR=/models/sam2 \
  sahool/sam2-inference:ci

curl -fsS http://localhost:18150/healthz
curl -sS http://localhost:18150/readyz || true
curl -sS http://localhost:18150/capabilities || true
docker logs sahool-sam2-ci --tail=100
docker stop sahool-sam2-ci
```

Expected without artifacts:

- `/healthz` returns 200.
- `/readyz` is not ready or reports missing SAM2 artifacts.
- No fake segmentation or fabricated polygon is produced.

P-CERT-4 artifact-present smoke:

```bash
docker run --rm -d \
  --name sahool-sam2-ci-model \
  -p 18151:8080 \
  -v "$PWD/artifacts/sam2:/models/sam2:ro" \
  -e SAM2_PRODUCTION_REQUIRED=true \
  -e SAM2_READINESS_MODE=strict \
  -e SAM2_MODEL_DIR=/models/sam2 \
  sahool/sam2-inference:ci

curl -fsS http://localhost:18151/readyz
curl -fsS http://localhost:18151/capabilities
docker stop sahool-sam2-ci-model
```

---

## 3. Additional services

### 3.1 auth

Build:

```bash
docker build \
  -f services/auth/Dockerfile \
  -t sahool/auth:ci \
  .
```

Required checks:

| Check | Criterion |
|---|---|
| Base image | exact pinned tag; current repository baseline is `python:3.11-slim-bookworm` |
| No `latest` | no `FROM ...:latest` |
| Non-root | `USER sahool` or equivalent non-root user |
| MFA runtime copied | `mfa_runtime.py` present in image |
| MFA router copied | `routers/mfa.py` present in image |
| Healthcheck | `/healthz`, not `/readyz` |
| JWT keys | mounted through `/app/keys` or configured through env; no key baked into image |

Runtime smoke:

```bash
docker run --rm -d \
  --name sahool-auth-ci \
  -p 18004:8000 \
  -e DATABASE_URL=postgresql://auth:auth@postgres:5432/auth \
  -e JWT_PRIVATE_KEY_PATH=/app/keys/jwt.pem \
  -v "$PWD/keys:/app/keys:ro" \
  sahool/auth:ci

curl -fsS http://localhost:18004/healthz
curl -sS http://localhost:18004/readyz || true
docker exec sahool-auth-ci python -c "import mfa_runtime; from routers import mfa; print('auth imports ok')"
docker logs sahool-auth-ci --tail=100
docker stop sahool-auth-ci
```

Security runtime evidence required for certification:

- RS256 token issue and verify.
- MFA TOTP anti-replay.
- Tenant isolation with `X-Tenant-ID`.
- No hardcoded private keys in `docker history`.

---

### 3.2 sahool-platform

Build:

```bash
docker build \
  -f services/sahool-platform/Dockerfile \
  -t sahool/sahool-platform:ci \
  .
```

Required checks:

| Check | Criterion |
|---|---|
| Base image | exact pinned tag |
| Non-root | `USER sahool` or equivalent |
| Healthcheck | `/healthz`, not `/readyz` |
| Routers copied | `api/routers/` exists in image |
| Direct routes in `api/main.py` | 0 direct `@app.get/post/put/delete` decorators |
| DB/Redis/NATS | configured by env only |

Runtime smoke:

```bash
docker run --rm -d \
  --name sahool-platform-ci \
  -p 18005:8000 \
  -e DATABASE_URL=postgresql://platform:platform@postgres:5432/platform \
  -e REDIS_URL=redis://redis:6379/0 \
  -e NATS_URL=nats://nats:4222 \
  sahool/sahool-platform:ci

curl -fsS http://localhost:18005/healthz
curl -sS http://localhost:18005/readyz || true
docker logs sahool-platform-ci --tail=100
docker stop sahool-platform-ci
```

Informational P3 checks only:

- `api/main.py` still contains embedded event/outbox and field/task/alert helper logic.
- P3 extraction is not required before current production-certification blockers are closed unless CI breaks.

---

### 3.3 odoo-bridge

Build:

```bash
docker build \
  -f services/odoo-bridge/Dockerfile \
  -t sahool/odoo-bridge:ci \
  .
```

Required checks:

| Check | Criterion |
|---|---|
| Base image | exact pinned tag |
| Non-root | `USER sahool` or equivalent |
| Runtime copied | `erp_runtime.py` present in image |
| Healthcheck | `/healthz`, not `/readyz` |
| Odoo connection | env-configured only |
| Tenant honesty | no hardcoded `tenant_id=1` bypass |

Runtime smoke:

```bash
docker run --rm -d \
  --name sahool-odoo-ci \
  -p 18126:8126 \
  -e ODOO_URL=http://odoo:8069 \
  -e ODOO_DB=production \
  -e ODOO_API_KEY=dummy \
  sahool/odoo-bridge:ci

curl -fsS http://localhost:18126/healthz
curl -sS http://localhost:18126/readyz || true
docker exec sahool-odoo-ci python -c "import erp_runtime; print('odoo imports ok')"
docker logs sahool-odoo-ci --tail=100
docker stop sahool-odoo-ci
```

---

## 4. Compose integration checks

Use the repository compose file, not a new hand-written compose snippet, unless intentionally creating a dedicated CI compose file.

```bash
docker compose -f docker-compose.v9.yml config
```

Then build selected services:

```bash
docker compose -f docker-compose.v9.yml build \
  sahool-raster-service \
  sahool-weather-service \
  sahool-edge \
  sahool-sam2-inference \
  sahool-auth \
  sahool-platform \
  sahool-odoo-bridge
```

Service names must match the compose file. If they drift, update the verifier manifest rather than inventing alternate names.

Cross-service smoke targets:

| From | To | Purpose |
|---|---|---|
| `sahool-platform` | `sahool-auth` | auth/verify dependency |
| `sahool-platform` | `sahool-raster-service` | raster/indicator facade |
| `sahool-platform` | `sahool-weather-service` | weather facade/raw weather |
| `vegetation-analysis-service` | `sahool-raster-service` | validated raster/NDVI path |
| `indicators-service` | `sahool-raster-service` | validated raster product path |

---

## 5. Evidence files

The automated verifier writes:

```text
certification/evidence/docker_build_matrix_full.json
certification/evidence/ci_summary.json
certification/evidence/model_provisioning_summary.json
```

Evidence must not mark production as verified unless the required phases actually ran.

Required fields per service:

```json
{
  "build": "pass|fail|skipped",
  "dockerfile": "services/.../Dockerfile",
  "image_size_mb": 0,
  "layers": 0,
  "healthcheck": "pass|fail|skipped",
  "readyz": "pass|degraded|fail|skipped",
  "security_scan": "pass|fail|skipped",
  "error": null
}
```

---

## 6. Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| DevOps Engineer |  |  |  |
| QA Lead |  |  |  |
| Security Reviewer |  |  |  |
| Geospatial Engineer |  |  |  |
| Release Manager |  |  |  |

---

## 7. Quick command summary

```bash
# Static verifier syntax only
python -m py_compile scripts/ci/docker_build_matrix_verifier.py
pytest -q tests_v9/test_docker_build_matrix_verifier_static.py

# Build selected critical services
python scripts/ci/docker_build_matrix_verifier.py \
  --services raster-service weather-service edge-inference sam2-inference \
  --write

# Build extended release-sensitive services
python scripts/ci/docker_build_matrix_verifier.py \
  --services raster-service weather-service edge-inference sam2-inference auth sahool-platform odoo-bridge \
  --write

# Build all Dockerfile-backed services discovered in services/
python scripts/ci/docker_build_matrix_verifier.py --all --write
```
