#!/usr/bin/env python3
"""Static ratchet for M4 governed VRI prescriptions."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
module = (ROOT / "services/sahool-platform/api/canonical_vri_prescription.py").read_text()
migration = (ROOT / "migrations/v180_governed_vri_prescription.sql").read_text()
for token in [
    "VRIPrescriptionZone",
    "GovernedVRIPrescription",
    "build_governed_vri_prescription",
    "COMPLETE_VRI_SOURCE_DIGESTS_REQUIRED",
    "COMMISSIONING_EXECUTABILITY_GATE_REQUIRED",
    "ZONE_APPLICATION_CAPPED_BY_RUNOFF_LIMIT",
    "VRI_HARD_CAPS_COULD_NOT_ALLOCATE_FULL_MPC_WATER_BUDGET",
    "recommendation_only=True",
    "execution_allowed=False",
    "translation_allowed=False",
    "vri_prescription_to_translation_input",
    "dispatch_allowed",
]:
    assert token in module, token
for token in [
    "vri_prescriptions",
    "vri_prescription_zones",
    "vri_machine_translation_artifacts",
    "vri_as_applied_variances",
    "recommendation_only BOOLEAN NOT NULL DEFAULT TRUE CHECK (recommendation_only = TRUE)",
    "execution_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (execution_allowed = FALSE)",
    "translation_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (translation_allowed = FALSE)",
    "dispatch_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (dispatch_allowed = FALSE)",
    "ENABLE ROW LEVEL SECURITY",
    "FORCE ROW LEVEL SECURITY",
    "WITH CHECK",
]:
    assert token in migration, token
for forbidden in ["mqtt.publish", "modbus.write", "actuator-service", "dispatch_allowed = true"]:
    assert forbidden not in module.lower(), forbidden
print("irrigation VRI M4 guard: PASS")
