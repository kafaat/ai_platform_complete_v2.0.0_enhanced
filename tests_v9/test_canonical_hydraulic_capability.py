import pytest
from api.canonical_hydraulic_capability import (
    build_canonical_hydraulic_capability,
    hydraulic_capability_to_mpc_constraints,
)


def _well():
    return {
        "status": "verified",
        "operational_eligible": True,
        "well_id": "well-1",
        "maximum_flow_lps": 60.0,
        "capability_digest": "a" * 64,
    }


def _pump():
    return {
        "pump_id": "pump-1",
        "certification_status": "certified",
        "motor_efficiency": 0.92,
        "curve_digest": "b" * 64,
        "curve_points": [
            {"flow_lps": 10.0, "head_m": 90.0, "efficiency": 0.68},
            {"flow_lps": 30.0, "head_m": 75.0, "efficiency": 0.78},
            {"flow_lps": 50.0, "head_m": 55.0, "efficiency": 0.72},
            {"flow_lps": 65.0, "head_m": 35.0, "efficiency": 0.60},
        ],
    }


def _segments():
    return [
        {
            "segment_id": "seg-1",
            "length_m": 900.0,
            "internal_diameter_mm": 200.0,
            "absolute_roughness_mm": 0.01,
            "minor_loss_k": 3.0,
            "pressure_rating_bar": 10.0,
            "maximum_velocity_m_s": 2.5,
            "certification_status": "certified",
            "segment_digest": "c" * 64,
        }
    ]


def test_builds_verified_hydraulic_capability():
    out = build_canonical_hydraulic_capability(
        tenant_id="t1",
        project_id="p1",
        well_capability=_well(),
        pump=_pump(),
        segments=_segments(),
        target={
            "target_asset_id": "pivot-1",
            "required_inlet_pressure_bar": 2.0,
            "elevation_gain_m": 8.0,
            "requested_flow_lps": 30.0,
            "terrain_profile_digest": "d" * 64,
        },
    )
    assert out.status == "verified"
    assert out.maximum_deliverable_flow_lps >= 30.0
    assert out.terminal_pressure_bar >= 2.0
    assert len(out.capability_digest) == 64
    constraints = hydraulic_capability_to_mpc_constraints(out)
    assert constraints["status"] == "available"


def test_blocks_uncertified_curve():
    pump = _pump()
    pump["certification_status"] = "draft"
    out = build_canonical_hydraulic_capability(
        tenant_id="t1",
        project_id="p1",
        well_capability=_well(),
        pump=pump,
        segments=_segments(),
        target={
            "target_asset_id": "x",
            "required_inlet_pressure_bar": 2.0,
            "elevation_gain_m": 0.0,
        },
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "certified_pump_curve_required"


def test_blocks_requested_flow_above_capability():
    out = build_canonical_hydraulic_capability(
        tenant_id="t1",
        project_id="p1",
        well_capability=_well(),
        pump=_pump(),
        segments=_segments(),
        target={
            "target_asset_id": "pivot-1",
            "required_inlet_pressure_bar": 5.0,
            "elevation_gain_m": 20.0,
            "requested_flow_lps": 60.0,
        },
    )
    assert out.status == "blocked"
    assert "REQUESTED_FLOW_EXCEEDS_HYDRAULIC_CAPABILITY" in out.blocking_reasons


pytestmark = pytest.mark.unit
