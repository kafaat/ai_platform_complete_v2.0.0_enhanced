from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "services" / "sahool-platform" / "api"
sys.path.insert(0, str(API))

from canonical_vri_prescription import (  # noqa: E402
    build_governed_vri_prescription,
    vri_prescription_to_translation_input,
)

D = "a" * 64


def _schedule(depth: float = 8.0, volume: float = 4000.0):
    return {
        "status": "verified",
        "recommendation_only": True,
        "scheduled_irrigation_mm": depth,
        "scheduled_volume_m3": volume,
        "schedule_digest": D,
    }


def _capability():
    return {
        "status": "verified",
        "maximum_safe_depth_mm_event": 12.0,
        "maximum_daily_depth_mm": 20.0,
        "irrigation_capability_digest": D,
        "sprinkler_capability_digest": D,
    }


def _gate():
    return {"status": "executable", "execution_allowed": True, "executability_digest": D}


def _geometry():
    return {
        "irrigated_area_ha": 50.0,
        "management_zone_set_digest": D,
        "machine_geometry_digest": D,
        "terrain_profile_digest": D,
    }


def _zones():
    return [
        {
            "zone_id": "z1",
            "area_ha": 25.0,
            "start_angle_deg": 0.0,
            "end_angle_deg": 180.0,
            "inner_radius_m": 0.0,
            "outer_radius_m": 400.0,
            "depletion_mm": 70.0,
            "raw_mm": 60.0,
            "taw_mm": 120.0,
            "eo_stress_score": 0.8,
            "slope_percent": 2.0,
            "infiltration_mm_h": 20.0,
            "maximum_safe_depth_mm": 10.0,
            "zone_digest": D,
        },
        {
            "zone_id": "z2",
            "area_ha": 25.0,
            "start_angle_deg": 180.0,
            "end_angle_deg": 360.0,
            "inner_radius_m": 0.0,
            "outer_radius_m": 400.0,
            "depletion_mm": 35.0,
            "raw_mm": 60.0,
            "taw_mm": 120.0,
            "eo_stress_score": 0.2,
            "slope_percent": 2.0,
            "infiltration_mm_h": 20.0,
            "maximum_safe_depth_mm": 10.0,
            "zone_digest": D,
        },
    ]


def _build(**overrides):
    args = {
        "tenant_id": "tenant-1",
        "field_id": "field-1",
        "season_id": "season-1",
        "machine_id": "machine-1",
        "hourly_mpc_schedule": _schedule(),
        "irrigation_capability": _capability(),
        "commissioning_gate": _gate(),
        "management_zones": _zones(),
        "machine_geometry": _geometry(),
    }
    args.update(overrides)
    return build_governed_vri_prescription(**args)


def test_builds_deficit_weighted_recommendation_only_prescription():
    result = _build()
    assert result.status == "verified"
    assert result.decision == "prescribe"
    assert result.execution_allowed is False
    assert result.translation_allowed is False
    assert len(result.prescription_digest) == 64
    assert result.zones[0]["target_depth_mm"] > result.zones[1]["target_depth_mm"]
    assert abs(result.prescribed_volume_m3 - 4000.0) < 1e-6


def test_excluded_zone_receives_zero_application():
    zones = _zones()
    zones[1]["excluded"] = True
    result = _build(management_zones=zones)
    excluded = next(zone for zone in result.zones if zone["zone_id"] == "z2")
    assert excluded["target_depth_mm"] == 0
    assert "EXCLUDED_ZONE_ZERO_APPLICATION" in excluded["reason_codes"]


def test_runoff_cap_can_degrade_when_full_budget_cannot_be_allocated():
    zones = _zones()
    for zone in zones:
        zone["maximum_safe_depth_mm"] = 1.0
        zone["slope_percent"] = 20.0
        zone["infiltration_mm_h"] = 2.0
    result = _build(management_zones=zones)
    assert result.status == "degraded"
    assert result.uncovered_budget_mm > 0
    assert "VRI_HARD_CAPS_COULD_NOT_ALLOCATE_FULL_MPC_WATER_BUDGET" in result.limitations


def test_blocks_missing_source_digest():
    geometry = _geometry()
    geometry["terrain_profile_digest"] = ""
    result = _build(machine_geometry=geometry)
    assert result.status == "blocked"
    assert "COMPLETE_VRI_SOURCE_DIGESTS_REQUIRED" in result.blocking_reasons


def test_blocks_non_executable_commissioning_gate():
    result = _build(
        commissioning_gate={
            "status": "blocked",
            "execution_allowed": False,
            "executability_digest": D,
        }
    )
    assert result.status == "blocked"
    assert "COMMISSIONING_EXECUTABILITY_GATE_REQUIRED" in result.blocking_reasons


def test_blocks_zone_area_above_machine_area():
    geometry = _geometry()
    geometry["irrigated_area_ha"] = 20.0
    result = _build(machine_geometry=geometry)
    assert result.status == "blocked"
    assert "VRI_ZONE_AREA_EXCEEDS_MACHINE_AREA" in result.blocking_reasons


def test_hold_schedule_produces_verified_empty_prescription():
    result = _build(hourly_mpc_schedule=_schedule(0.0, 0.0))
    assert result.status == "verified"
    assert result.decision == "hold"
    assert result.zones == []


def test_translation_input_remains_non_dispatchable():
    result = _build()
    translated = vri_prescription_to_translation_input(result)
    assert translated["status"] == "available"
    assert translated["translation_allowed"] is False
    assert translated["dispatch_allowed"] is False


pytestmark = pytest.mark.unit
