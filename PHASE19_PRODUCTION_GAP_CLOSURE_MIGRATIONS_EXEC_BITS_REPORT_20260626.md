# Phase 19 — Production Gap Closure: Migration Consistency, Exec Bits, and Env Doctor Robustness

## Scope

This patch closes the production blockers found during direct source review after Phase 18.

## Fixes

1. `scripts/runtime/env_doctor.py` now tolerates unreadable PATH entries and `PermissionError` while checking command availability.
2. Critical shell-script invocations in GitHub Actions and local gates now use `bash script.sh`, so CI is not dependent on executable bits after ZIP extraction.
3. Executable permissions were restored on all operational `.sh` scripts.
4. `scripts_v9/migrate.py` is now manifest-driven and no longer stops at the historical v9/v13 list.
5. `scripts_v9/run_migrations.sql` was regenerated from `migrations/MANIFEST.txt`.
6. Runtime activation migrations with duplicated numeric prefixes were renumbered to `v114`–`v121` and references/tests were updated.
7. Added `scripts/migrations/validate_migration_manifest.py` and wired it into the production gate, local quality gate, env doctor, and CI validation.
8. `migrations/MANIFEST.md` now mirrors the text manifest instead of carrying a stale partial list.

## Validation

- `python -m py_compile` passed for modified assets.
- `scripts/migrations/validate_migration_manifest.py --root .` passed.
- `scripts/ci/validate_ci_gates.py --root .` passed.
- `bash scripts/production_validation_gate.sh` passed.
- Focused regression tests passed.

## Remaining Non-Code Runtime Work

The codebase still requires live Docker/Kubernetes execution with real secrets, migrations against a real PostgreSQL/PostGIS database, and live E2E/load/chaos runs before it can be called production-validated.
