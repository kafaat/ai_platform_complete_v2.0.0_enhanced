# SAHOOL → Unified Local Lab: ML scientific-screen candidate bridge (DEV)

**Status:** additive read-only candidate adapter. **Not a production endpoint**, not a migration, not a model training job, not a sensor verifier, not a water-ledger change, not an actuator interface.

- `shared/feature_store/ml_quality_bridge.py::export_ml_quality_candidate` emits a document compatible with the existing [Unified Local Lab pinned evaluator](https://github.com/kafaat/unified-local-lab/blob/956c9eb668fac78ebe6cd30bde26aed229ab2556/src/portable_ci_lab/ml_quality.py) `ml-quality/v1` input. It is a standalone helper, not automatically wired into the Phase 10 API.
- All required source timestamps are timezone-aware: `feature_event_at ≤ feature_available_at ≤ prediction_at < label_measured_at ≤ label_available_at ≤ dataset_freeze_at`. The Lab enforces further field-group disjointness and temporal embargo. These constraints are not claims of source authenticity.
- Only `soil_sensor` and `field_measurement` are potentially independent outcome sources. `derived_ledger_balance`, operator estimates and missing receipts are rejected. `label_source` is **never** marked `*_verified` if no trusted application-supplied `receipt_verifier` callback is available. A callback must verify actual evidence bytes, authoritative ownership, tenant/field/season/source, case ID, measured-at timestamp and numerical target depth; this module only uses its boolean result and never independently authenticates real measurements.
- A well-formed receipt SHA-256 may be used for **only one row per export**, including after a failed verification attempt. A repeated receipt blocks the export with `MEASUREMENT_RECEIPT_REUSED`; changing its case ID, measured-at time or target depth must cause the trusted verifier to fail. The callback receives 8 arguments in order: `tenant_id, field_id, season_id, measurement_origin, measurement_receipt_sha256, case_id, label_measured_at, target_mm` (time normalized as ISO 8601; depth in millimeters as float).
- Rows rejected for malformed schema, timestamps or depth are omitted from exported `rows`; rows that fail measurement-source or receipt verification remain as `label_source=unverified_claim`. Both cases make the overall adapter status `BLOCKED`, while `input_count` and `row_count` report the difference.
- The returned `status=CANDIDATE_NOT_EVALUATED` means **the input preparation phase is ready for scientific testing**, not the model itself. Even after `SCIENTIFIC_SCREEN_PASSED` in the Lab, release requires the existing Decision Service and independent human gates.
- It deliberately does not reuse `point_in_time_safe` from the existing feature-store dataset manifest because that flag checks event-time presence, not independently witnessed availability time.
- This PR does not add a route that accepts caller-supplied tenant identity, and does not expose unredacted field sensor observations. Integration with a live authoritative database and the Lab runner requires a separate, tenant-enforced adapter and real acceptance evidence.

## Local contract check

```bash
PYTHONPATH=. python -m pytest -q tests/phase6/test_ml_quality_bridge.py
```

All fixtures are synthetic. The tests establish the bridge contract only; no real databases, providers, models or actuators are exercised.
