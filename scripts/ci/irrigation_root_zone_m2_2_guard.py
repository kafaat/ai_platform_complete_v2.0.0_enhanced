#!/usr/bin/env python3
"""Static ratchet for M2.2 canonical root-zone hydraulics."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/v169_canonical_root_zone_hydraulic_profile.sql"
PRODUCT = ROOT / "services/sahool-platform/api/canonical_root_zone_profile.py"
WATER = ROOT / "services/sahool-platform/api/canonical_water_state.py"

migration = MIGRATION.read_text(encoding="utf-8")
product = PRODUCT.read_text(encoding="utf-8")
water = WATER.read_text(encoding="utf-8")

for table in ("crop_root_policies", "canonical_root_zone_profiles"):
    assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
assert migration.count("FORCE ROW LEVEL SECURITY") >= 2
assert "current_setting('app.current_tenant_id'" in migration
for token in (
    "soil_profile_does_not_cover_root_depth",
    "validated_crop_root_policy_missing",
    "governed_soil_hydraulic_profile_missing",
    "field_capacity_weighted",
    "infiltration_mm_h",
    "profile_digest",
):
    assert token in product, token
assert "resolve_canonical_root_zone_profile" in water
assert "soil_water_params" not in water
print("irrigation root-zone M2.2 guard: PASS")
