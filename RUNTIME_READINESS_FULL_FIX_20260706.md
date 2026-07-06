# SAHOOL Runtime Readiness Full Fix — 2026-07-06

## Scope

This patch completes the deeper component hardening pass requested after the S3/Compose fixes. It focuses on preventing startup races and UI synchronization drift without changing business behavior.

## Changes Applied

### 1. Qdrant readiness contract

Updated `docker-compose.v9.yml` and `docker-compose.fixed.yml`:

- Added a healthcheck to `sahool-qdrant`.
- Changed Qdrant dependents from `service_started` to `service_healthy`:
  - `sahool-local-ai-rag`
  - `sahool-rag-retrieval`
  - `sahool-qdrant-seed`

This prevents RAG/seed services from racing Qdrant before port 6333 is ready.

### 2. Worker healthchecks

Added explicit healthchecks for long-running workers in `docker-compose.v9.yml`:

- `sahool-raster-backfill-scan-worker`
- `sahool-raster-cache-invalidation-worker`
- `sahool-phase-runtime-outbox-worker`
- `sahool-plugin-runtime-worker`
- `sahool-model-registry-worker`
- `sahool-actuator-dispatch-worker`

The healthchecks are intentionally low-risk and validate that required DB configuration is present inside each worker container. They do not change worker commands or data paths.

### 3. Backfill UI polling hardening

Updated `frontend/src/sections/MapHub.tsx`:

- Added a `backfillPollTokenRef` cancellation token.
- Cancels stale polling when the selected field changes.
- Cancels polling when the component unmounts.
- Retries transient backfill status polling errors up to 5 times.
- Performs a final best-effort Timeline/available-dates refresh in `finally`.
- Prevents stale polling from clearing busy state for a newer run.

This prevents old `run_id` polling loops from updating the Timeline for the wrong field.

### 4. CI guard

Added `scripts/ci/runtime_readiness_contract_gate.py` and wired it into `.github/workflows/ci.yml`.

The gate fails if:

- Qdrant loses its healthcheck.
- RAG/seed services stop waiting for `sahool-qdrant: service_healthy`.
- Critical worker services lose healthchecks.
- MapHub loses abort/retry/final-sync backfill polling protections.

## Verification Performed

Static checks passed in this environment:

```text
python3 -m py_compile scripts/ci/runtime_readiness_contract_gate.py
python3 scripts/ci/minio_s3_contract_gate.py
python3 scripts/ci/compose_env_contract_gate.py
python3 scripts/ci/backfill_ui_sync_gate.py
python3 scripts/ci/runtime_readiness_contract_gate.py
python3 scripts/ci/service_port_gate.py
python3 scripts/ci/nginx_compose_dns_gate.py
python3 scripts/ci/v9_gpu_contract_gate.py
python3 scripts/ci/runtime_contract_gate.py
Python compile sweep: 1726 files compiled successfully
YAML parse: docker-compose*.yml and .github/workflows/ci.yml OK
No S3_SECRET_KEY required interpolation remains in compose files
```

## Runtime Verification Still Required Locally

Docker daemon is not available in this execution environment, so run locally:

```powershell
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu config
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu build --no-cache
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu up -d
```

Then verify:

```powershell
docker ps --format "table {{.Names}}	{{.Status}}"
docker logs v21-sahool-qdrant-1 --tail 100
docker logs v21-sahool-raster-backfill-scan-worker-1 --tail 100
```

## Expected Result

- `docker compose config` should not fail on S3 interpolation.
- Qdrant should become healthy before RAG/seed services start.
- Worker containers should expose health status instead of showing no healthcheck.
- Backfill Timeline should remain synchronized even if the user changes fields during an active historical imagery pull.

---

## Correction applied during integration (verify-before-merge)

The original proposal added an in-container healthcheck to `sahool-qdrant`
(`bash -lc 'exec 3<>/dev/tcp/127.0.0.1/6333'`) and set RAG/seed dependents to
`condition: service_healthy`. This is **incorrect for this deployment**: the
`qdrant/qdrant` image is **distroless** (no shell/curl), so the probe can never run
and marks Qdrant permanently "unhealthy", which deadlocks every `service_healthy`
dependent (RAG stack down). This regression was already documented in
`docker-compose.fixed.yml`.

**Correction:** Qdrant has **no** in-container healthcheck; its dependents gate on
`service_started`. Project-owned workers keep their healthchecks (their images have a
shell). The CI gate now enforces the *inverse* contract (Qdrant must NOT declare a
healthcheck; dependents must use `service_started`). A true Qdrant readiness gate, if
needed later, belongs in a sidecar probe or the RAG service's own retry/backoff — not
a self-healthcheck inside the distroless image.
