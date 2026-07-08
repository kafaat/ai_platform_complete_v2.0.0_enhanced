# P4 Decision / Outcome / Learning Boundary Extraction Report

## Scope
Implemented the P4 boundary layer after P3.4. The extraction is performed as a safe service-boundary step rather than a destructive code move.

## Added
- `services/decision-service/main.py`
- `services/decision-service/requirements.txt`
- `services/decision-service/tests/test_p4_decision_service_runtime.py`
- `services/sahool-platform/api/decision_service_client.py`
- `services/sahool-platform/tests/test_p4_decision_boundary_extraction_guard.py`
- `docs/architecture/DECISION_SERVICE_BOUNDARY_CONTRACT.md`

## Ownership changes
The loop tables are now registered to `decision-service` in `docs/architecture/db_ownership.yml`:
- decision_record
- dispatch_decisions
- outcome_record
- recommendation_outcomes
- online_learning_updates
- recommendation_feedback (deprecated)

## Status
The platform now has a dedicated BFF client for decision-service calls. Historical platform routers remain present for compatibility but are bounded by a new architectural contract and ownership guard. The next hardening step is P4.5: convert the legacy write routers one-by-one to call the facade and then remove direct DB writes.
