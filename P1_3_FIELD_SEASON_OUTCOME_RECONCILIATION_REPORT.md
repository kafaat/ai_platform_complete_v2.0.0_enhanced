# P1.3 Field Season Outcome Reconciliation Read Path

## Scope

This patch wires the existing Decision/Outcome/Learning bridge into the seasonal operational truth
read path instead of leaving reconciled outcomes visible only in `/api/v1/learning/summary`.

## Changed files

- `services/sahool-platform/api/field_season_projection.py`
- `services/sahool-platform/api/routers/seasons.py`
- `services/sahool-platform/tests/test_field_season_projection_reconciled_outcomes.py`
- `services/sahool-platform/tests/test_p1_decision_outcome_learning_bridge_guard.py`
- `docs/architecture/DECISION_OUTCOME_LEARNING_BRIDGE_CONTRACT.md`

## Runtime behavior

`GET /api/v1/fields/{field_id}/seasons/{season_id}/state` now reads, best-effort:

- `outcome_record` filtered by `field_id`
- `recommendation_outcomes` filtered by `field_id` and `season_id`
- `dispatch_decisions` for recommendation→decision soft linking

The route passes those rows into `assemble_field_season_state`, which exposes:

- `outcome_reconciliation.total`
- `outcome_reconciliation.decided`
- `outcome_reconciliation.pending`
- `outcome_reconciliation.success_rate`
- `outcome_reconciliation.sample_count`
- `outcome_reconciliation.by_source`
- `outcome_reconciliation.by_kind`
- `outcome_reconciliation.linked_group_count`

## Truthfulness rules

- Pending recommendation outcomes do not increase `sample_count`.
- Pending recommendation outcomes do not enter `success_rate`.
- Missing outcome evidence is explicit through `evidence_missing` as `outcomes`.
- The output shows whether evidence came from `outcome_record`, `recommendation_outcomes`, or both.

## Verification

Targeted tests:

```bash
cd /mnt/data/work_p13
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
  services/sahool-platform/tests/test_learning_summary_reconciled_outcomes.py \
  services/sahool-platform/tests/test_field_season_projection.py \
  services/sahool-platform/tests/test_field_season_projection_reconciled_outcomes.py \
  tests_v9/test_learning_summary.py
```

Result: `82 passed`.
