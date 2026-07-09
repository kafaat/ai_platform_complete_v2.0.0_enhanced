# Production Certification + Platform Sub-Inventory Correction Report — 2026-07-09

## Purpose

This report applies the requested correction to the final post-P2 inventory without reopening P0/P1/P2.

## Corrections Applied

### 1. Reclassified embedded business logic in `sahool-platform/api/main.py`

The previous report correctly stated that `services/sahool-platform/api/main.py` has zero direct route decorators, so P1 remains complete. However, two large categories were too generically described as bootstrap/compatibility surface.

They are now explicitly classified as embedded business logic:

| Category | LOC | Correct classification |
|---|---:|---|
| `idempotency_outbox_events` | 390 | `embedded_business_logic` |
| `field_task_alert_helpers` | 268 | `embedded_business_logic` |

Combined embedded business logic still present in platform main:

```text
658 LOC
```

This does not change the P1 decision because direct routes remain zero. It does make the future P3 work a real business-runtime extraction rather than cosmetic bootstrap cleanup.

Recommended future P3 modules:

```text
api/platform_events_runtime.py
api/platform_field_alert_runtime.py
```

### 2. Added residual-line transparency

The platform sub-inventory now reports an estimated uncategorized/residual line count after imports and categorized top-level symbols. This is explicitly marked for review before any P3 extraction plan is finalized.

### 3. Documented the skipped test

The known local skipped test is now documented in the production certification checklist:

```text
services/weather-service/tests/test_weather_redis_live_optional.py
```

Reason:

```text
Skipped unless WEATHER_REDIS_INTEGRATION_URL is set.
```

Certification impact:

```text
Acceptable for local/offline guard runs.
Not acceptable as final production certification evidence.
Maps directly to P-CERT-3 Redis live integration.
```

### 4. Added recommended blocker closure order

The production certification checklist now states the closure order:

```text
1. P-CERT-2 — Connected transitive lock generation
2. P-CERT-1 — Full branch CI
3. P-CERT-4 — ONNX/SAM2 model provisioning
4. P-CERT-3 — Redis live integration
```

## Files Updated

```text
scripts/ci/platform_main_subinventory_guard.py
scripts/ci/production_certification_checklist_guard.py
platform_main_subinventory.generated.json
platform_main_subinventory.csv
PLATFORM_MAIN_SUBINVENTORY_20260709.md
production_certification_checklist.generated.json
production_certification_checklist.csv
docs/runbooks/PRODUCTION_CERTIFICATION_CHECKLIST.md
PRODUCTION_CERTIFICATION_PLATFORM_SUBINVENTORY_CORRECTION_REPORT_20260709.md
```

## Verification

```bash
pytest -q \
  tests_v9/test_production_certification_checklist_guard.py \
  tests_v9/test_platform_main_subinventory_guard.py

python scripts/ci/platform_main_subinventory_guard.py --check
python scripts/ci/production_certification_checklist_guard.py --check
python scripts/ci/p1_main_decomposition_guard.py
python scripts/ci/p2_main_decomposition_guard.py
python scripts/ci/route_mount_contract_guard.py --check
python scripts/ci/api_versioning_policy_guard.py --check
python scripts/ci/test_requirements_inventory_guard.py --check
```

Confirmed result:

```text
2 passed
platform_main_subinventory_check_ok
production_certification_checklist_ok
p1_main_decomposition_guard_ok
p2_main_decomposition_guard_ok
route_mount_inventory_check_ok
api_versioning_policy_check_ok
test_dependency_inventory_check_ok
```

## Final Decision

```text
P0/P1/P2 remain complete.
Production certification remains blocked until external evidence closes P-CERT-1..4.
Platform main.py is route-free but contains 658 LOC of embedded business logic; this is a P3 extraction target after certification blockers.
```
