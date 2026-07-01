# V49.5 — Field Memory / Evidence Hardening

Base package: `sahool_v9.1.0_75ba7f9_v62_2_runtime_evidence_wiring.zip`

## Scope

This patch hardens the pre-agent field memory and evidence context introduced around v49 before the v55+ tool harness and v58+ provider-native agent consume it.

## Implemented changes

### Field AI context hardening

File:

- `services/sahool-platform/api/routers/field_ai_context.py`

Changes:

- Added explicit tenant filter to `_optional_events`:
  - `WHERE tenant_id = $2::uuid`
  - call site now passes `str(user.tenant_id)`.
- Added context redaction before context is returned/injected into AI:
  - secrets/tokens/api keys
  - emails/phones/mobile/SMS/WhatsApp fields
  - owner/registry identifiers
  - signed/file URLs
  - long free-text truncation
- Added item budgets:
  - events: 120
  - drawing features: 80
  - alerts: 40
  - recommendations: 40
- Added final byte budget and last-resort compaction:
  - `_CONTEXT_MAX_BYTES = 36000`
  - `readiness.context_budget`
- Added source provenance cards:
  - events
  - drawing_features
  - alerts
  - recommendations
  - imagery_timeline
  - weather_history
- Added evidence freshness scoring:
  - per section where timestamps exist
  - aggregate `readiness.evidence_freshness_score`
- Removed raw payload pass-through for events by redacting payload before exposure.

### Recommendation outcomes RLS/data contract hardening

File:

- `migrations/v49_5_evidence_context_hardening.sql`

Changes:

- Keeps RLS enabled and forced on `recommendation_outcomes`.
- Replaces `tenant_isolation` with both `USING` and `WITH CHECK`.
- Adds NOT VALID constraints for safe rollout:
  - `tenant_id IS NOT NULL`
  - `predicted_yield_t_ha >= 0` when present
  - `actual_yield_t_ha >= 0` when present
- Adds tenant/field/season supporting index.

This migration is intentionally safe/idempotent and leaves actual `VALIDATE CONSTRAINT` for a cleanup/DB integration campaign.

### Tests

File:

- `tests_v9/test_field_ai_context_hardening_v49_5.py`

Guards:

- explicit tenant-scoped events query
- redaction and budget controls
- freshness and provenance cards
- recommendation outcome RLS migration contract

## Verification

Python compile:

```text
py_compile passed
```

Targeted v49.5 + v55-v62.2 guard suite:

```text
114 passed
```

Command used:

```bash
python3 -m pytest -q \
  tests_v9/test_field_ai_context_hardening_v49_5.py \
  services/sahool-platform/tests/test_field_ai_context_v45_static.py \
  tests_v9/test_ai_tool_registry_v55.py \
  tests_v9/test_ai_tool_executor_v55.py \
  tests_v9/test_ai_tool_loop_v56.py \
  tests_v9/test_ai_tool_loop_chat_integration_v57.py \
  tests_v9/test_ai_provider_native_tool_calling_v58.py \
  tests_v9/test_ai_provider_native_multiround_audit_v58.py \
  tests_v9/test_ai_approval_endpoints_v58.py \
  tests_v9/test_field_boundary_ai_v59.py \
  tests_v9/test_field_boundary_adapters_v59_1.py \
  tests_v9/test_field_boundary_backends_v59_5.py \
  tests_v9/test_productivity_zones_v60.py \
  tests_v9/test_productivity_zones_clustering_v60_1.py \
  tests_v9/test_soil_sampling_planner_v61.py \
  tests_v9/test_soil_sampling_strategies_v61_1.py \
  tests_v9/test_vra_prescription_engine_v62.py \
  tests_v9/test_prescription_export_adapters_v62_1.py \
  tests_v9/test_runtime_evidence_wiring_v62_2.py
```

## Honest limitations

- This patch hardens the Python/API contract and adds safe SQL constraints, but it does not run a live PostgreSQL migration validation campaign.
- `VALIDATE CONSTRAINT` is not executed here because that requires a real database with existing data cleanup.
- It does not yet implement v57.5/v58.2c governance hardening; that remains the next recommended branch after v49.5.

## Recommended next step

Proceed to:

```text
v57.5 / v58.2c — Agent Governance Hardening
```

Recommended scope:

- durable audit store required in `/chat`
- persistent approval store
- total tool budget + dedupe
- stop-on-pending-approval
- strict registry↔executor mutating→approval invariant
- tool result sanitizer
- CI gates for tool harness governance
