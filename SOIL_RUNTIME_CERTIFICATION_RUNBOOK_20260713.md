# Soil Runtime Certification Runbook

## Purpose

Certify the canonical soil truth chain on PostgreSQL before enabling `docker-compose.soil-strict.yml`.

## Automated CI evidence

The integration suite now proves on a migrated real PostgreSQL/PostGIS instance:

1. v155/v156 tables exist.
2. RLS is enabled and forced on canonical soil and laboratory tables.
3. `tenant_isolation` includes both `USING` and `WITH CHECK`.
4. A `NOSUPERUSER NOBYPASSRLS` role sees only its tenant and cannot write another tenant.
5. Sixteen concurrent writes sharing one idempotency key persist exactly one observation.
6. Twelve concurrent profile rebuilds converge on one profile hash and one persisted snapshot.
7. Cutover readiness changes from blocked to ready only after the valid profile exists.

Test file: `tests_v9/test_soil_runtime_certification_integration.py`.

## Cutover procedure

1. Apply the migration manifest with `ON_ERROR_STOP=1`.
2. Run `pytest -v -m integration tests_v9/test_soil_runtime_certification_integration.py`.
3. For every production tenant, call `GET /v1/soil/cutover/readiness` using the service token and tenant header.
4. Require `can_enable_strict_soil=true`, zero missing profiles and zero invalid profiles.
5. Start with the strict override:

```bash
docker compose -f docker-compose.v9.yml -f docker-compose.soil-strict.yml up -d
```

6. Run decision and AgriAI smoke requests against fields with baseline, guided and verified profiles.
7. Keep the base compose files unchanged for rollback; remove the strict override to return to safe mode.

## Fail-closed conditions

Do not enable strict mode when migrations are absent, evidence exists without a profile, any profile hash is invalid, a profile quality gate fails, or tenant coverage is below 100% for fields carrying canonical evidence.
