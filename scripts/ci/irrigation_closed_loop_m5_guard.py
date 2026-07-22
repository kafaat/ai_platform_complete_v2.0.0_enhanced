#!/usr/bin/env python3
"""Static ratchet for M5 irrigation closed-loop learning and certification."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
module = (ROOT / "services/sahool-platform/api/irrigation_closed_loop_learning.py").read_text()
migration = (
    ROOT / "migrations/v181_irrigation_closed_loop_learning_production_certification.sql"
).read_text()
for token in [
    "IrrigationOutcomeEvidence",
    "GovernedLearningProposal",
    "IrrigationClosedLoopRecord",
    "ProductionCertificationResult",
    "build_irrigation_closed_loop_record",
    "propose_governed_irrigation_learning",
    "certify_irrigation_production_runtime",
    "COMPLETE_CLOSED_LOOP_LINEAGE_REQUIRED",
    "RECONCILED_WATER_LEDGER_EVENT_REQUIRED",
    '"auto_adjust": False',
    "REQUIRED_PRODUCTION_GATES",
]:
    assert token in module, token
for token in [
    "irrigation_outcome_evidence",
    "irrigation_closed_loop_records",
    "irrigation_learning_proposals",
    "irrigation_production_certifications",
    "auto_adjust BOOLEAN NOT NULL DEFAULT FALSE CHECK (auto_adjust = FALSE)",
    "production_certified BOOLEAN NOT NULL DEFAULT FALSE",
    "ENABLE ROW LEVEL SECURITY",
    "FORCE ROW LEVEL SECURITY",
    "WITH CHECK",
]:
    assert token in migration, token
for forbidden in ["mqtt.publish", "modbus.write", "actuator-service", "auto_adjust = true"]:
    assert forbidden not in module.lower(), forbidden
print("irrigation closed-loop M5 guard: PASS")
