#!/usr/bin/env python3
"""Static ratchet for M2.11 canonical as-applied irrigation truth."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
module = (ROOT / "services/sahool-platform/api/canonical_as_applied_irrigation.py").read_text(encoding="utf-8")
migration = (ROOT / "migrations/v178_canonical_as_applied_irrigation_truth.sql").read_text(encoding="utf-8")
for token in [
    "AuthorizedIrrigationPlan",
    "IrrigationExecutionReceipt",
    "AsAppliedObservation",
    "CanonicalAsAppliedIrrigationTruth",
    "build_canonical_as_applied_irrigation_truth",
    "as_applied_truth_to_water_ledger_event",
    "AS_APPLIED_VOLUME_VARIANCE_EXCEEDS_TOLERANCE",
    "POSITION_COVERAGE_BELOW_ACCEPTANCE_THRESHOLD",
    "water_ledger_eligible=verified",
    "decision_content_digest",
    "commissioning_certification_digest",
]:
    assert token in module, token
for token in [
    "as_applied_irrigation_runs",
    "as_applied_irrigation_receipts",
    "as_applied_irrigation_observations",
    "canonical_as_applied_irrigation_truths",
    "ENABLE ROW LEVEL SECURITY",
    "FORCE ROW LEVEL SECURITY",
    "WITH CHECK",
    "as_applied_digest CHAR(64)",
    "UNIQUE (tenant_id, controller_id, sequence_number)",
]:
    assert token in migration, token
for forbidden in ["mqtt.publish", "modbus.write", "actuator-service", "dispatch_allowed = true"]:
    assert forbidden not in module.lower(), forbidden
print("irrigation as-applied M2.11 guard: PASS")
