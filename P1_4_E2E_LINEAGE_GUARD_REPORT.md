# P1.4 E2E Lineage Guard Report

## Scope

Implemented a pure E2E lineage guard for the closed loop:

```text
recommendation
→ dispatch decision
→ decision record
→ outcome_record / recommendation_outcomes
→ learning source lineage
→ learning summary
→ field season state projection
```

This is not a new feature and does not split services. It is a regression guard that proves the bridge built in P1/P1.1/P1.3 is not paper-only.

## Added

```text
services/sahool-platform/tests/test_p1_4_recommendation_to_learning_lineage_e2e.py
```

## Updated

```text
docs/architecture/DECISION_OUTCOME_LEARNING_BRIDGE_CONTRACT.md
```

## Guarded behavior

- Clean loop: known recommendation, dispatch, decision, outcome, and recommendation outcome are linked.
- `dispatch_decisions` links `recommendation_id` to `decision_id` for reconciled outcome grouping.
- `resolve_learning_source` must mark a complete recommendation outcome source as `traceable` and `applies=True`.
- `learning_summary` must count reconciled decided outcomes and expose `linked_group_count`.
- `field_season_state_projection` must expose the same reconciled outcome evidence.
- Pending/unmatured recommendation outcomes remain visible, but they do not increase `sample_count` or `success_rate`.
- Missing source id yields `pending_review` and `applies=False`.

## Result

The P1.4 guard is ready to run with the existing P0/P1/P1.1/P1.3 test set.
