# SAHOOL Phase 4 — Production Hardening + Security + Observability

## Scope

This patch hardens the Phase 12 runtime after Phase 3 E2E integration by focusing on production safety, failure visibility, and operational checks.

## Implemented changes

### 1. Secrets and DB role hardening

- Sanitized the committed `.env` file so it contains placeholders only.
- Preserved the restricted application role convention:
  - `DATABASE_URL` uses `sahool_app`.
  - `JOBS_DATABASE_URL` uses `sahool_jobs`.
- Added `scripts/security_audit.sh` to fail on committed high-risk secrets and unsafe DB role patterns:
  - Telegram bot token pattern.
  - CDSE/Sentinel secrets.
  - generated JWT/service tokens.
  - `POSTGRES_USER=postgres` as application user.
  - application `DATABASE_URL` using `postgres` or `sahool_user`.
  - `sslmode=disable`.

### 2. AI runtime fail-closed behavior

- `ai_agronomist` now fails closed for field-specific advice when `CanonicalFieldState` is unavailable or not found.
- This prevents field-specific AI answers from silently falling back to generic context when the field context is missing.
- The service remains evidence-only and does not emit operational decisions.

### 3. Observability endpoints

Added Prometheus-compatible `/metrics` endpoints for:

- `services/ai_agronomist/main.py`
- `services/rag-retrieval/main.py`
- `services/knowledge-graph/main.py`

These complement existing `/healthz` and `/readyz` endpoints.

### 4. Runtime smoke scripts

Added:

- `scripts/observability_smoke.sh`
  - Checks ready/metrics endpoints through the gateway.
- `scripts/outbox_reliability_check.sh`
  - Checks the outbox DLQ endpoint when `SAHOOL_JWT` is available.
  - Optionally queries `event_outbox` through `psql` when `DATABASE_URL` is available.

### 5. Regression tests

Added:

- `tests/security/test_phase4_security_observability_contracts.py`

This test suite verifies:

- committed `.env` is placeholder-only;
- security audit script covers core secret/role risks;
- AI runtime exposes metrics and fails closed for missing field context;
- RAG/KG expose readiness and metrics;
- observability/outbox scripts exist and target the correct endpoints;
- compose keeps restricted DB roles and AI readiness contracts.

## Verification performed

- Python compile: `1329 compiled, 0 failed`.
- Phase 4 + Phase 3 regression tests: `11 passed`.
- Compose YAML static parse: `44 services`.
- Security audit script: passed hard failures; emitted advisory BYPASSRLS comments as warnings only.

## Remaining runtime-only verification

Docker is not available in this execution environment, so the following must be run locally:

```bash
docker compose -f docker-compose.v9.yml config
docker compose -f docker-compose.v9.yml up -d
./scripts/security_audit.sh
BASE_URL=http://localhost ./scripts/observability_smoke.sh
SAHOOL_JWT=<jwt> BASE_URL=http://localhost ./scripts/outbox_reliability_check.sh
```

## Production note

The remaining BYPASSRLS references are documented job/bootstrap/guard contexts. The important production invariant is still:

- application traffic uses `sahool_app`;
- background cross-tenant jobs use `sahool_jobs`;
- migrations/bootstrap may use the owner/admin role only during controlled migration execution.
