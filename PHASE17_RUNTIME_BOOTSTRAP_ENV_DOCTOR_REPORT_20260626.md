# Phase 17 — Runtime Bootstrap & Production Environment Doctor

## Scope

This phase adds a dependency-light runtime doctor that can be executed before and after local Docker Compose or Kubernetes deployment. It is designed to detect production-blocking configuration drift before operators run expensive end-to-end, load, or chaos tests.

## Added assets

- `scripts/runtime/env_doctor.py`
- `scripts/runtime/runtime_doctor.sh`
- `tests/runtime/test_phase17_runtime_bootstrap_doctor.py`

## Checks covered

- Required bootstrap assets are present.
- Runtime environment variables exist and do not use placeholder-like secrets.
- `DATABASE_URL` uses the `sahool_app` runtime role.
- `JOBS_DATABASE_URL` uses the `sahool_jobs` role.
- Required migrations v106–v112 are registered.
- Compose contains the critical runtime services.
- Compose avoids `image: latest`, `POSTGRES_USER=postgres`, and `SAHOOL_ALLOW_RLS_BYPASS_ROLE` runtime exposure.
- Docker Compose config is executed when Docker is available; otherwise it is explicitly marked as skipped.
- Local ports are scanned to warn about possible conflicts.
- Runtime HTTP health and metrics endpoints are checked when `--mode runtime` or `--mode full` is used.
- Static production gates can be run together with `--mode full`.

## Operator commands

```bash
# Static preflight; safe before starting services
python scripts/runtime/env_doctor.py --mode preflight --format text

# Runtime checks after docker compose up
BASE_URL=http://localhost python scripts/runtime/env_doctor.py --mode runtime --format text

# Full gates + runtime checks, with JSON report
MODE=full BASE_URL=http://localhost ./scripts/runtime/runtime_doctor.sh
```

## Result

The doctor does not replace the existing security, release, Helm, observability, load, chaos, or E2E gates. It orchestrates and explains readiness at the environment boundary, which was the remaining gap between release packaging and real deployment operation.
