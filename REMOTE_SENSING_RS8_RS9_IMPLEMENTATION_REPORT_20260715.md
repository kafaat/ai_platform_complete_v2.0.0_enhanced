# Remote Sensing RS-8 / RS-9 Implementation Report

## Scope

Implemented on top of the RS-6/RS-7 archive without adding routes to `sahool-platform`.

## RS-8 — Diagnosis and Decision Bridge

- Added `diagnosis_engine.py` in vegetation-analysis-service.
- Diagnosis generation is allowed only for anomalies in `confirmed` state.
- Signal types are mapped to explicit hypotheses; diagnosis remains a hypothesis and contains no prescription.
- Ground-verification evidence is represented through immutable evidence URNs.
- Added `/v1/anomalies/{anomaly_ref}/diagnoses`.
- Added `decision_bridge.py` and `/v1/anomalies/{anomaly_ref}/decision-referrals`.
- The bridge first writes an immutable vegetation snapshot to decision-service, then records a decision candidate.
- Vegetation transitions to `decision_referred` only after decision-service accepts both writes.
- When decision-service is in its current mirror/non-authoritative mode, the snapshot endpoint returns 503 and the bridge exposes 424. No false referral success is recorded.
- Decision-service continues to own review, approval, dispatch, execution and outcome state.

## RS-9 — Workspace BFF

Added a standalone service:

`services/remote-sensing-workspace-bff`

Single endpoint:

`GET /v1/fields/{field_id}/remote-sensing-workspace`

Supported sections:

- overview
- timeline
- anomalies
- ground
- decisions
- compare

Properties:

- Forwards Authorization and X-Tenant-Id to owning services.
- Aggregates indicators-service, vegetation-analysis and decision-service.
- Ground section is honest and reports `task_service_not_configured` when no task service URL exists.
- Upstream partial failures are surfaced in `partial` and `errors`; they are not silently converted to empty success.
- Unknown section names fail with 422.
- Added to `docker-compose.v9.yml` as `sahool-remote-sensing-workspace-bff`.
- No new route was added to sahool-platform, preserving the route budget.

## Verification

- Relevant regression suite: 63 passed, 0 failed.
- Python compileall: passed.
- Compose YAML parse and static wiring gates: passed.

## Honest runtime boundary

The code path is complete, but an authoritative live decision referral requires:

- decision-service database migrations applied;
- `DECISION_SERVICE_SOR_ENABLED=true`;
- `DECISION_SERVICE_DATABASE_URL` configured;
- service-to-service authentication configured;
- actual field-state references supplied by the seasonal state owner.

Until those conditions are met, decision referral fails closed by design.
