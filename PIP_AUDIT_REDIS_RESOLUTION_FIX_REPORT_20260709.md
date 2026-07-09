# PIP Audit Redis Resolution Fix — 2026-07-09

## Trigger

GitHub Actions job `86218990714` failed before `pip-audit` could audit packages:

```text
ResolutionImpossible: Cannot install redis==5.2.1, redis==5.3.1 and redis>=5.0.0
```

The failure was a resolver conflict across the combined critical-path `pip-audit` command, not a runtime regression.

## Root cause

Different requirement files participating in CI/pip-audit declared incompatible Redis constraints:

- `services/sahool-platform/api/requirements.txt` → `redis==5.3.1`
- `services/weather-service/requirements.txt` → `redis==5.2.1`
- several services/tests → `redis==5.0.0`
- root/dev/bot requirements → `redis>=5.0.0`

Because the CI command resolves these files together, direct pins for the same shared package must converge.

## Fix

Unified Redis to a single direct version:

```text
redis==5.3.1
```

Updated files include:

- `requirements_real.txt`
- `requirements-dev.txt`
- `tests_v9/requirements-test.txt`
- `bots/telegram/requirements.txt`
- `services/actuator-service/requirements.txt`
- `services/auth/requirements.txt`
- `services/guardrails-engine/requirements.txt`
- `services/raster-service/requirements.txt`
- `services/sahool-platform/api/requirements.txt`
- `services/tts-service/requirements.txt`
- `services/video-processor/requirements.txt`
- `services/weather-service/requirements.txt`

## Regression guard

Added:

```text
scripts/ci/pip_audit_resolution_guard.py
tests_v9/test_pip_audit_resolution_guard.py
.github/workflows/pip-audit-resolution-guard.yml
```

The guard fails if Redis is reintroduced as a mismatched pin/range in files that are co-installed by CI or participate in the critical `pip-audit` path.

The guard is also included in:

```text
scripts/ci/runtime_real_smoke.sh
```

## Verification

Commands run:

```bash
python scripts/ci/pip_audit_resolution_guard.py
pytest -q tests_v9/test_pip_audit_resolution_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/build_service_dependency_bundle.py --check
python scripts/ci/test_requirements_inventory_guard.py --check
```

Results:

```text
pip_audit_resolution_guard_ok
1 passed
 dependency_inventory_check_ok
 dependency_conflict_inventory_check_ok
 direct_dependency_bundle_check_ok
 test_dependency_inventory_check_ok
```

`runtime_real_smoke.sh` static guards reached and passed the new guard; the full script timed out later during the broad pytest phase in this chat environment, so the new tests were rerun separately and passed.

## Current status

The known Redis resolver conflict is closed. The next CI run should not fail with:

```text
Cannot install redis==5.2.1, redis==5.3.1 and redis>=5.0.0
```
