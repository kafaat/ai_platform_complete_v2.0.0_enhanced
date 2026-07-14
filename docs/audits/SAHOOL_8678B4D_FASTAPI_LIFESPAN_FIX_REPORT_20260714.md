# SAHOOL 8678b4d — FastAPI Lifespan Regression Fix

Date: 2026-07-14

## Scope

This patch fixes the FastAPI lifecycle regression identified in `sahool_ai_platform_8678b4d_green(1).zip`.

## Changes

- Replaced all seven deprecated `@app.on_event("startup"/"shutdown")` hooks in `services/sahool-platform/api/main.py` with one `asynccontextmanager` lifespan.
- Preserved startup order: JWT warning → DB pools → scheduler → outbox relay.
- Preserved reverse shutdown order: outbox relay → scheduler → DB pools.
- Cleanup is executed from `finally`, including partially-started application states.
- Added `scripts/ci/fastapi_lifespan_guard.py`.
- Wired the guard into `.github/workflows/ci.yml`.

## Verification

- Python compilation: PASS.
- FastAPI lifespan guard: PASS.
- Irrigation M2.1–M2.11, M3, M4, M5 and canonical RLS guards: PASS.
- Migration manifest: PASS, 189 migrations.
- Focused MPC/VRI regression with deprecation warnings promoted to errors: 76 passed, 0 failed, 0 warnings.

Command:

```bash
PYTHONPATH=services/sahool-platform pytest -q \
  -W error::DeprecationWarning \
  tests_v9/test_irrigation_mpc.py \
  tests_v9/test_lexicographic_irrigation_mpc.py \
  tests_v9/test_lexicographic_mpc_bridge.py \
  tests_v9/test_hourly_energy_aware_irrigation_mpc.py \
  tests_v9/test_canonical_vri_prescription.py
```

## Remaining boundary

This patch closes the lifecycle warning regression only. It does not claim that M2.3–M5 are fully assembled into a live production orchestration route, nor that PostgreSQL/staging E2E certification has been completed.
