# Guardrails validation contract

`POST /v1/validate` approves an actionable proposal. An informational explanation
does not constitute approval. The caller supplies the authenticated tenant UUID
and the canonical `users.id` (positive PostgreSQL INTEGER); ASCII decimal strings
are normalized for compatibility. Boolean, fractional and opaque IDs are rejected.

Missing or malformed evidence returns HTTP 422 before any tier runs. Monetary
values use USD, must be finite nonnegative JSON numbers, and cannot be numeric
strings or booleans. An explicit zero revenue is accepted as evidence but requires
human review because financial capacity cannot be established from it.

| Action | Required action data | Required financial context |
| --- | --- | --- |
| investment, irrigation, fertilization, pesticide | `cost_usd`, `projected_revenue_increase_usd` | `annual_revenue_usd`, `annual_costs_usd`, `cash_reserve_usd` |
| loan | `loan_amount_usd` | `annual_revenue_usd`, `current_debt_usd` |
| contract | `contract_value_usd` | `annual_revenue_usd` |

Irrigation additionally requires `water_m3`, positive `field_area_ha`, measured
`season_water_used_m3_ha`, and a supported `water_source`. Pesticide validation
requires `chemical` and `dosage_kg_ha`. Numeric parameters consumed by the tiers
are validated when present. Policy thresholds remain in the tier classes.

Only LOW risk with all tiers passing and `auto_approve_low_risk=true` can be
approved automatically. MEDIUM warnings and an explicit request for manual review
are persisted as review workflows. No missing financial input is silently filled
with zero. Callers without an authoritative financial evidence source must keep
the proposal pending; that integration is needed before full approval is available.

Every workflow operation uses a transaction with both tenant GUCs set locally.
Workflow creation returns an ID only after the transaction commits. An unavailable
store returns HTTP 503 with `approval_store_unavailable`. Approval/rejection use
row locks, enforce the persisted specialty role, reject expired workflows, and
count each expert once. Existing explicit admin authority is retained; a generic
`expert` role does not acquire all specialist permissions. Changed action parameters
require new validation rather than approval of an unreviewed modification.

Notification transport is not configured. Responses explicitly report
`notification_delivery: "not_configured"`; persisted workflow status is available
through `GET /v1/workflow/{workflow_id}`. No delivery or live PostgreSQL certification
is implied by unit tests. The restricted-role integration case is in
`tests_v9/test_db_wiring.py::TestHILGetStatus` and requires a migrated PostgreSQL instance.
