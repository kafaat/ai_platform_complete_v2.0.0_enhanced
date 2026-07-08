# P1.1 Outcome Reconciler Read-Path Wiring Report

## Scope

This patch connects the previously pure `core.outcome_reconciler` into a real read path: `/api/v1/learning/summary`.

## Changes

Modified:

- `services/sahool-platform/core/outcome_reconciler.py`
  - Added top-level `region` propagation for both normalized outcome models.
  - Kept source-specific semantics intact: `outcome_record` = decision effect; `recommendation_outcomes` = yield learning.

- `services/sahool-platform/api/learning_summary.py`
  - Added `_learning_row_from_unified_outcome`.
  - Added `summarize_learning_with_reconciled_outcomes`.
  - Exposes `outcome_reconciliation` metadata: `by_source`, `by_kind`, `linked_group_count`, `authoritative_note`.

- `services/sahool-platform/api/routers/learning_summary.py`
  - Reads `outcome_record` as the primary model.
  - Best-effort reads `recommendation_outcomes` and `dispatch_decisions`.
  - Missing optional bridge tables do not hide `outcome_record` evidence and do not cause a 503.

- `docs/architecture/DECISION_OUTCOME_LEARNING_BRIDGE_CONTRACT.md`
  - Added read-path wiring rules.

Added:

- `services/sahool-platform/tests/test_learning_summary_reconciled_outcomes.py`
  - Verifies both outcome models contribute to the learning summary.
  - Verifies immature recommendation outcomes stay pending and do not inflate evidence.

Updated:

- `services/sahool-platform/tests/test_p1_decision_outcome_learning_bridge_guard.py`
  - Ensures the reconciler is wired into the learning summary read path and not left as pure-only code.

## Validation

P0 + P1 boundary/bridge test set:

```bash
PYTHONPATH=services/sahool-platform pytest -q \
  services/sahool-platform/tests/test_p0_platform_route_ownership_guard.py \
  services/sahool-platform/tests/test_p0_db_ownership_guard.py \
  services/sahool-platform/tests/test_p0_platform_module_growth_guard.py \
  services/sahool-platform/tests/test_p1_raster_boundary_guard.py \
  services/sahool-platform/tests/test_p1_weather_boundary_guard.py \
  services/sahool-platform/tests/test_p1_decision_outcome_learning_bridge_guard.py \
  services/sahool-platform/tests/test_learning_source_lineage.py \
  services/sahool-platform/tests/test_outcome_reconciler.py \
  services/sahool-platform/tests/test_loop_referential_integrity.py \
  services/sahool-platform/tests/test_learning_summary_reconciled_outcomes.py
```

Result: `55 passed`.

Endpoint wiring check:

```bash
PYTHONPATH=services/sahool-platform pytest -q \
  services/sahool-platform/tests/test_learning_summary_endpoint.py
```

Result: `3 passed`.

Attempted legacy `tests_v9/test_learning_summary.py`; it could not run in this environment because `python-jose` / `jose` is not installed in the container test environment. No source failure was observed there.

## Result

The decision/outcome/learning bridge is now connected to a real dashboard read path. Learning summaries can see both outcome models with explicit provenance, while unresolved yield-learning outcomes remain pending and do not inflate evidence.
