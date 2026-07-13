#!/usr/bin/env python3
"""Static ratchet for the M2.1 irrigation engineering foundation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/v168_irrigation_engineering_foundation.sql"
CONTRACTS = ROOT / "services/sahool-platform/api/irrigation_engineering_contracts.py"

migration = MIGRATION.read_text(encoding="utf-8")
contracts = CONTRACTS.read_text(encoding="utf-8")

required_tables = (
    "irrigation_projects",
    "irrigation_water_sources",
    "irrigation_wells",
    "irrigation_pumps",
    "irrigation_mainlines",
    "irrigation_machines",
    "irrigation_controllers",
    "irrigation_energy_systems",
)
for table in required_tables:
    assert f"CREATE TABLE IF NOT EXISTS {table}" in migration, table

assert migration.count("FORCE ROW LEVEL SECURITY") >= 1
assert "current_setting('app.current_tenant'" in migration
assert "credential_reference" in migration
assert "password|secret|token" in migration
assert (
    "design_state" in migration and "commissioned_state" in migration and "live_state" in migration
)
assert "class IrrigationProjectContract" in contracts
assert "class IrrigationMachineContract" in contracts
assert "class EnergySystemContract" in contracts
assert 'extra="forbid"' in contracts
assert "reject_inline_secrets" in contracts
print("irrigation engineering M2.1 guard: PASS")
