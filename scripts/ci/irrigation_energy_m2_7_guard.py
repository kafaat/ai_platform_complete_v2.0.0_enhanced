#!/usr/bin/env python3
"""Repository ratchet for M2.7 energy/microgrid capability."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {
    "migrations/v174_energy_agricultural_microgrid_capability.sql": [
        "irrigation_pv_arrays",
        "irrigation_battery_systems",
        "irrigation_energy_loads",
        "canonical_energy_capabilities",
        "hourly_energy_envelopes",
        "FORCE ROW LEVEL SECURITY",
    ],
    "services/sahool-platform/api/canonical_energy_microgrid_capability.py": [
        "STARTING_KVA_LIMIT_EXCEEDED",
        "BATTERY_BMS_NOT_READY",
        "battery reserve protected",
        "energy_capability_to_mpc_constraints",
        "renewable_fraction",
    ],
}
for file_name, tokens in REQUIRED.items():
    text = (ROOT / file_name).read_text()
    for token in tokens:
        assert token in text, (file_name, token)
print("irrigation energy M2.7 guard: PASS")
