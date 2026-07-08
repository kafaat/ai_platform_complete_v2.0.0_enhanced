# P1 Decision / Outcome / Learning Bridge Contract

Purpose: keep the recommendation loop traceable while `sahool-platform` still hosts legacy runtime routes.
This is a bridge contract, not a full extraction. The target ownership remains:

| Capability | Current host | Target owner | Rule |
|---|---|---|---|
| recommendation scoring | `sahool-platform` facade / `agriai-engine` | `agriai-engine` | platform may expose compatibility routes, but scoring/output truth belongs to `agriai-engine` |
| decision record | `sahool-platform` legacy writer | `agriai-engine` / future decision service | every decision must retain `decision_id` and tenant context |
| dispatch/execution ledger | `sahool-platform` legacy writer | operations/actuator boundary | dispatch must link `recommendation_id -> decision_id -> execution_id` when present |
| outcome measurement | `sahool-platform` legacy writer | `agriai-engine` / future outcome service | outcome rows must link to `decision_id` or recommendation outcome lineage |
| learning update | `sahool-platform` legacy writer | learning-service target | no learning update is trusted without source lineage |

## Hard bridge rules

1. `online_learning_updates` must carry explicit source lineage:
   `source_type`, `source_id`, `field_id`, `season_id`, `recommendation_id`, `decision_id`,
   `evidence_snapshot_id`, and `traceability_status`.
2. `traceable` is the only status that may apply policy/model change. Untraceable updates are stored for audit,
   but treated as `rejected_untraceable` or `pending_review`.
3. `recommendation_feedback` is deprecated and must not gain a new writer. Permanent feedback belongs in the live
   reference models: `recommendation_outcomes`, `farm_operations_ledger`, and `water_ledger`.
4. `outcome_record` and `recommendation_outcomes` are not duplicate truth. They must be reconciled through
   `core.outcome_reconciler` when a combined read model is needed.
5. Hard database foreign keys are intentionally not added to cross-service loop identifiers. Integrity is checked by
   read-side reconciliation (`core.loop_referential_integrity`) because identifiers are soft cross-service lineage IDs.

## Guarded artifacts

- `core.learning_source_lineage`
- `core.outcome_reconciler`
- `core.loop_referential_integrity`
- `migrations/v151_learning_source_lineage.sql`
- `migrations/v152_deprecate_recommendation_feedback.sql`
- `services/sahool-platform/tests/test_p1_decision_outcome_learning_bridge_guard.py`

## Events to preserve

```text
recommendation.created.v1
decision.approved.v1
operation.dispatched.v1
operation.verified.v1
outcome.measured.v1
learning.updated.v1
```

Bridge closure criterion: a learning update is never silently trusted unless it can be traced to a source outcome,
execution feedback, recommendation outcome, or explicit human feedback.

## P1.1 Read-path wiring — learning summary

`core.outcome_reconciler` is now consumed by `api.learning_summary.summarize_learning_with_reconciled_outcomes`.
The learning dashboard read path no longer reads `outcome_record` alone when optional bridge tables are present:

- `outcome_record` remains authoritative for decision-effect outcomes.
- `recommendation_outcomes` contributes yield-learning outcomes.
- `dispatch_decisions` provides a soft `recommendation_id -> decision_id` link when present.
- Missing optional bridge tables are treated as zero bridge rows, not as fabricated data and not as a dashboard outage.
- The response exposes `outcome_reconciliation.by_source`, `by_kind`, and `linked_group_count` so the UI can see source composition instead of silently merging two semantically different models.

Evidence inflation guard: unresolved recommendation outcomes stay `success=None` and contribute `n_evaluated=0` to evidence counters until a real actual yield exists.

## P1.3 Read-path wiring: Field Season State Projection

`api.field_season_projection.assemble_field_season_state` consumes reconciled outcome inputs in
addition to agronomic/EO/weather/water signals:

- `outcome_records` from `outcome_record` for decision-effect evidence.
- `recommendation_outcomes` from `recommendation_outcomes` for yield-learning evidence.
- `dispatch_links` from `dispatch_decisions` for soft recommendation→decision linking.

The projection exposes `outcome_reconciliation` with source mix, kind mix, decided/pending counts,
`success_rate`, `sample_count`, and `linked_group_count`. Pending or immature recommendation outcomes
remain pending and never increase `sample_count` or `success_rate`. Absence of outcome evidence is
reported through `evidence_missing` as `outcomes`; it is not fabricated.

## P1.4 E2E Lineage Guard

A pure in-process E2E guard now protects the full loop contract:

```
recommendation -> dispatch_decision -> decision_record -> outcome_record / recommendation_outcomes -> online_learning_update source lineage -> learning_summary -> field_season_state_projection
```

Required guarantees:

- a dispatch row must point to a known recommendation before the loop is considered clean;
- an outcome row must point to a known decision before the loop is considered clean;
- `recommendation_outcomes` must link to `decision_id` through `dispatch_decisions` when that bridge exists;
- pending / immature recommendation outcomes are visible, but never increase `sample_count` or `success_rate`;
- a learning update must be traceable (`source_type` + `source_id`) before it can apply a policy/model update;
- both read paths, `learning/summary` and `field_season_state_projection`, must expose reconciled outcome metadata.

Guard file:

```
services/sahool-platform/tests/test_p1_4_recommendation_to_learning_lineage_e2e.py
```

