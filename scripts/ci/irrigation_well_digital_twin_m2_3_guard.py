#!/usr/bin/env python3
"""Static ratchet for M2.3 water-source and well digital twin."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/v170_water_source_well_digital_twin.sql"
PRODUCT = ROOT / "services/sahool-platform/api/canonical_well_capability.py"

migration = MIGRATION.read_text(encoding="utf-8")
product = PRODUCT.read_text(encoding="utf-8")

for table in (
    "irrigation_well_pumping_tests",
    "irrigation_well_measurements",
    "irrigation_water_quality_samples",
    "irrigation_water_allocations",
    "canonical_well_capabilities",
):
    assert f"CREATE TABLE IF NOT EXISTS {table}" in migration, table
assert migration.count("FORCE ROW LEVEL SECURITY") >= 1
assert "current_setting('app.current_tenant'" in migration
for token in (
    "certified_pumping_test_required",
    "WELL_MEASUREMENT_STALE",
    "DRAWDOWN_LIMIT_EXCEEDED",
    "DAILY_WATER_ALLOCATION_EXHAUSTED",
    "WATER_SALINITY_LIMIT_EXCEEDED",
    "capability_digest",
    "well_capability_to_mpc_constraints",
):
    assert token in product, token
assert "/ 86.4" in product, "daily m3 to average L/s conversion must use 86.4"
print("irrigation well digital twin M2.3 guard: PASS")
