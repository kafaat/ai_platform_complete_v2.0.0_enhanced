import pytest
from api.canonical_sprinkler_runoff_capability import (
    build_canonical_sprinkler_runoff_capability,
    sprinkler_capability_to_mpc_constraints,
)


def _machine():
    return {
        "status": "verified",
        "operational_eligible": True,
        "machine_id": "m1",
        "capability_digest": "a" * 64,
    }


def _root():
    return {
        "quality_status": "verified",
        "operational_eligible": True,
        "infiltration_mm_h": 15.0,
        "root_zone_refill_cap_mm": 12.0,
        "profile_digest": "b" * 64,
    }


def test_verified_low_runoff_package():
    out = build_canonical_sprinkler_runoff_capability(
        tenant_id="t1",
        project_id="p1",
        machine_capability=_machine(),
        package={
            "package_id": "sp1",
            "certification_status": "certified",
            "tested_peak_application_mm_h": 9.0,
            "test_quality": "certified",
            "test_digest": "c" * 64,
        },
        root_zone_profile=_root(),
        terrain={"maximum_slope_percent": 2.0, "quality": "certified", "profile_digest": "d" * 64},
        weather={"wind_speed_m_s": 2.0, "quality": "measured", "snapshot_digest": "e" * 64},
    )
    assert out.status == "verified"
    assert out.runoff_safety_factor > 1.0
    assert sprinkler_capability_to_mpc_constraints(out)["status"] == "available"


def test_blocks_runoff_risk():
    root = _root()
    root["infiltration_mm_h"] = 5.0
    out = build_canonical_sprinkler_runoff_capability(
        tenant_id="t1",
        project_id="p1",
        machine_capability=_machine(),
        package={
            "package_id": "sp1",
            "certification_status": "certified",
            "tested_peak_application_mm_h": 12.0,
            "test_quality": "certified",
        },
        root_zone_profile=root,
        terrain={"maximum_slope_percent": 10.0, "quality": "certified"},
        weather={"wind_speed_m_s": 2.0, "quality": "measured"},
    )
    assert out.status == "blocked"
    assert "RUNOFF_RISK_HIGH" in out.blocking_reasons


pytestmark = pytest.mark.unit
