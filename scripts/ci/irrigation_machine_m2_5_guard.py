#!/usr/bin/env python3
"""Repository ratchet for M2.5 irrigation machine capability."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
required = {
    "migrations/v172_irrigation_machine_capability.sql": [
        "canonical_irrigation_machine_capabilities",
        "irrigation_machine_spans",
        "FORCE ROW LEVEL SECURITY",
    ],
    "services/sahool-platform/api/canonical_irrigation_machine_capability.py": [
        "8.64",
        "maximum_daily_depth_mm",
        "CONTROLLER_STATUS_TELEMETRY_REQUIRED",
    ],
}
for file, tokens in required.items():
    text = (ROOT / file).read_text()
    for token in tokens:
        assert token in text, (file, token)
print("irrigation machine M2.5 guard: PASS")
