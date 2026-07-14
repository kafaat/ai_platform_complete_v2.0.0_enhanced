#!/usr/bin/env python3
"""Ratchet for the server-owned irrigation runtime orchestrator."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
service = (ROOT / "services/sahool-platform/api/irrigation_runtime_orchestrator.py").read_text()
router = (ROOT / "services/sahool-platform/api/routers/irrigation_mpc.py").read_text()
required = [
    "resolve_canonical_water_state",
    "canonical_irrigation_capability_graphs",
    "irrigation_executability_gates",
    "solve_hourly_energy_aware_mpc",
    "hourly_irrigation_mpc_schedules",
    "recommendation_only",
    "execution_allowed",
    "server_owned_canonical_truth",
]
for token in required:
    assert token in service, token
assert "/api/v1/fields/{field_id}/irrigation/mpc/hourly-recommendation" in router
for forbidden in ("mqtt.publish", "modbus.write", "actuator dispatch", "dispatch_allowed = true"):
    assert forbidden not in service.lower(), forbidden
print("irrigation runtime orchestrator guard: PASS")
