#!/usr/bin/env python3
"""Static ratchet for M2.10 irrigation commissioning certification."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
module = (
    ROOT / "services/sahool-platform/api/irrigation_commissioning_certification.py"
).read_text(encoding="utf-8")
migration = (ROOT / "migrations/v177_irrigation_commissioning_certification.sql").read_text(encoding="utf-8")

required_module_tokens = [
    "REQUIRED_EVIDENCE_TYPES",
    "REQUIRED_SAFETY_CHECKS",
    "build_irrigation_commissioning_certification",
    "apply_commissioning_executability_gate",
    "COMMISSIONING_CAPABILITY_DIGEST_MISMATCH",
    "COMMISSIONING_CERTIFICATION_EXPIRED",
    "INDEPENDENT_REVIEWER_MUST_DIFFER",
    '"execution_allowed": executable',
]
required_migration_tokens = [
    "irrigation_commissioning_evidence",
    "irrigation_commissioning_certifications",
    "irrigation_executability_gates",
    "ENABLE ROW LEVEL SECURITY",
    "FORCE ROW LEVEL SECURITY",
    "WITH CHECK",
    "irrigation_capability_digest CHAR(64)",
    "certification_digest CHAR(64)",
    "executability_digest CHAR(64)",
]
for token in required_module_tokens:
    assert token in module, token
for token in required_migration_tokens:
    assert token in migration, token
assert "mqtt.publish" not in module.lower()
assert "modbus" not in module.lower()
assert "actuator-service" not in module.lower()
print("irrigation commissioning M2.10 guard: PASS")
