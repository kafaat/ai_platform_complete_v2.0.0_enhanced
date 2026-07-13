#!/usr/bin/env python3
"""Repository ratchet for M2.4 hydraulic capability."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
required = {
    "migrations/v171_pump_hydraulic_network_capability.sql": [
        "canonical_hydraulic_capabilities",
        "FORCE ROW LEVEL SECURITY",
        "internal_diameter_mm",
        "pressure_rating_bar",
    ],
    "services/sahool-platform/api/canonical_hydraulic_capability.py": [
        "_darcy_friction_factor",
        "specific_energy_kwh_m3",
        "INSUFFICIENT_PUMP_HEAD",
        "capability_digest",
    ],
}
for file, tokens in required.items():
    text = (ROOT / file).read_text()
    for token in tokens:
        assert token in text, (file, token)
print("irrigation hydraulic M2.4 guard: PASS")
