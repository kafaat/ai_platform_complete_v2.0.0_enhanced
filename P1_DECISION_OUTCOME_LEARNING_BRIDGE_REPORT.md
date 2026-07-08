# P1 Decision / Outcome / Learning Bridge — Implementation Report

Implemented on top of P1 Weather Boundary.

## Added

- `docs/architecture/DECISION_OUTCOME_LEARNING_BRIDGE_CONTRACT.md`
- `docs/architecture/decision_outcome_learning_bridge_allowlist.json`
- `services/sahool-platform/tests/test_p1_decision_outcome_learning_bridge_guard.py`

## What the new guard proves

1. The bridge contract exists and states the non-negotiable loop rules.
2. The learning source lineage, outcome reconciler, and referential-integrity bridge modules exist.
3. `online_learning_updates` writer resolves source lineage before insert and persists source columns.
4. Migration `v151_learning_source_lineage.sql` adds source columns, closed source types, traceability status,
   and an index for untraceable updates.
5. Deprecated `recommendation_feedback` remains deprecated and cannot gain a silent runtime writer.
6. Loop tables are registered in `db_ownership.yml` with a single writer/owner.
7. Decision/outcome/learning routes in `platform_extraction_map.json` must have approved target owners.

## Important boundary decision

This phase does not extract decision runtime from `sahool-platform`. It locks the loop first:
recommendation → decision → dispatch/execution → verification → outcome → traceable learning.

The next safe step is to expose/use the unified outcome read model from `core.outcome_reconciler` in the field-season
projection/read path, then gradually move decision scoring and learning writes behind service clients.
