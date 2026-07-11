# WX-10.8 Reviewer / Approvals UI — Implementation Report

## Baseline

- Source archive: `sahool_2122978_main_tip.zip`
- This increment is additive and leaves WX-10.7 state-machine, migration 002, and review transaction unchanged.

## Implemented

### Decision-Service

- `GET /v1/decisions/review-queue`
- SoR-only and fail-closed (`503`) in mirror mode.
- Tenant-scoped query over `decision_record`.
- Uses only `stage='candidate'` and dedicated `review_state='pending_approval'`.
- Returns immutable candidate evidence and canonical `candidate_lineage_id`.

### Platform BFF

- `GET /api/v1/decisions/review-queue`
- Protected by `Permission.DECISION_APPROVE`.
- Rejects non-authoritative, non-persisted, or malformed queue responses.
- Existing review POST remains a thin authoritative pass-through.

### Reviewer UI

- Added authoritative candidate queue to `ApprovalsConsolePage`.
- Displays decision type, field, confidence, creation time, concise evidence summary, and lineage.
- Approve/reject actions call the WX-10.7 review endpoint.
- Reject reason is mandatory.
- Each attempt receives a unique idempotency key.
- Mirror/service failures are displayed honestly; no misleading empty queue fallback.
- No dispatch, task, equipment, actuator, or automatic execution was added.

### Coverage governance

- Removed `WAIVER-WX10.7-001` for the review POST endpoint.
- Added real UI coverage entries for the review queue and review transition.

## Verification

- Python compile: PASS
- JSON validation: PASS
- Focused backend/BFF/review/coverage tests: `26 passed`
- Endpoint UI coverage gate: included in the 26 and PASS
- Frontend TypeScript CI remains required because the extracted archive contains no `node_modules`.

## Production caveat

The queue and transition intentionally return `503` until the operator-owned Decision-Service SoR promotion is completed. This increment does not flip ownership or enable SoR.
