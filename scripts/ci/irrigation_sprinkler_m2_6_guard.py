#!/usr/bin/env python3
"""Repository ratchet for M2.6 sprinkler/runoff capability."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
required = {
    "migrations/v173_sprinkler_runoff_capability.sql": [
        "canonical_sprinkler_runoff_capabilities",
        "irrigation_sprinkler_packages",
        "FORCE ROW LEVEL SECURITY",
    ],
    "services/sahool-platform/api/canonical_sprinkler_runoff_capability.py": [
        "RUNOFF_RISK_HIGH",
        "maximum_safe_depth_mm_event",
        "CURRENT_WIND_MEASUREMENT_REQUIRED",
    ],
}
for file, tokens in required.items():
    text = (ROOT / file).read_text()
    for token in tokens:
        assert token in text, (file, token)
print("irrigation sprinkler M2.6 guard: PASS")
