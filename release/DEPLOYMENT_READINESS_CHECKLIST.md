# SAHOOL Deployment Readiness Checklist — 2026-06-26

## Pre-release gates

- [ ] `docker compose -f docker-compose.v9.yml config`
- [ ] `./scripts/production_validation_gate.sh`
- [ ] `./scripts/security_audit.sh`
- [ ] `python scripts/observability/validate_observability_assets.py`
- [ ] `python scripts/release/build_release_bundle.py`
- [ ] `python scripts/release/validate_release_package.py`

## Runtime smoke

- [ ] `docker compose -f docker-compose.v9.yml up -d`
- [ ] `./scripts/check_gateway_routes.sh`
- [ ] `BASE_URL=http://localhost ./scripts/runtime_smoke.sh`
- [ ] `SAHOOL_JWT=<jwt> TENANT_ID=<tenant> FIELD_ID=<field> BASE_URL=http://localhost ./scripts/e2e/e2e_field_imagery_ai.sh`

## Reliability validation

- [ ] `./scripts/load/run_load_tests.sh`
- [ ] `./scripts/chaos/run_chaos_tests.sh`
- [ ] `./scripts/recovery/recovery_smoke.sh`

## Go/no-go conditions

Deployment is blocked if any of these are true:

- Runtime `DATABASE_URL` uses `postgres`, `sahool_user`, or a BYPASSRLS role.
- Required migrations v106 through v112 are missing from `migrations/MANIFEST.txt`.
- Grafana dashboards or Prometheus alert rules fail validation.
- RAG/KG/AI paths silently fallback instead of returning degraded/fail-closed state.
- Raster TileJSON responses omit date/cache-version isolation.
- Release checksum validation fails.
