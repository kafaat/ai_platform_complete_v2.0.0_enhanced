#!/usr/bin/env python3
"""Static ratchet for M3 hourly energy-aware irrigation MPC."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
module = (ROOT / "services/sahool-platform/api/hourly_energy_aware_irrigation_mpc.py").read_text(encoding="utf-8")
migration = (ROOT / "migrations/v179_hourly_energy_aware_irrigation_mpc.sql").read_text(encoding="utf-8")
for token in [
    "HourlyMPCAction",
    "HourlyEnergyAwareMPCSchedule",
    "solve_hourly_energy_aware_mpc",
    "COMMISSIONING_EXECUTABILITY_GATE_REQUIRED",
    "NO_FEASIBLE_HOURLY_ENERGY_WINDOW",
    "COMPLETE_CANONICAL_SOURCE_DIGESTS_REQUIRED",
    "ENERGY_CONSTRAINED",
    "execution_allowed=False",
    "recommendation_only=True",
    "schedule_digest",
]:
    assert token in module, token
for token in [
    "hourly_irrigation_mpc_schedules",
    "hourly_irrigation_mpc_actions",
    "execution_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (execution_allowed = FALSE)",
    "ENABLE ROW LEVEL SECURITY",
    "FORCE ROW LEVEL SECURITY",
    "WITH CHECK",
    "schedule_digest CHAR(64)",
    "UNIQUE (tenant_id, schedule_id, action_hour)",
]:
    assert token in migration, token
for forbidden in ["mqtt.publish", "modbus.write", "actuator-service", "dispatch_allowed = true"]:
    assert forbidden not in module.lower(), forbidden
print("irrigation hourly MPC M3 guard: PASS")
