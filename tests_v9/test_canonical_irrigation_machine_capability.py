import pytest
from api.canonical_irrigation_machine_capability import (
    build_canonical_irrigation_machine_capability,
    machine_capability_to_mpc_constraints,
)


def test_pivot_application_formula_and_constraints():
    out = build_canonical_irrigation_machine_capability(
        tenant_id="t1",
        project_id="p1",
        machine={
            "machine_id": "m1",
            "machine_type": "center_pivot",
            "certification_status": "certified",
            "effective_area_ha": 50.0,
            "design_flow_lps": 50.0,
            "full_cycle_hours": 10.0,
            "minimum_speed_percent": 20.0,
            "maximum_speed_percent": 100.0,
            "required_inlet_pressure_bar": 2.0,
            "certificate_digest": "a" * 64,
        },
        hydraulic_capability={
            "status": "verified",
            "operational_eligible": True,
            "maximum_deliverable_flow_lps": 55.0,
            "terminal_pressure_bar": 2.5,
            "capability_digest": "b" * 64,
        },
        controller={
            "certification_status": "certified",
            "capabilities": {"read_status": True, "read_position": True},
            "certificate_digest": "c" * 64,
        },
    )
    assert out.status == "verified"
    assert out.application_rate_mm_day == 8.64
    assert out.depth_per_full_cycle_mm == 3.6
    assert machine_capability_to_mpc_constraints(out)["status"] == "available"


def test_blocks_insufficient_flow():
    out = build_canonical_irrigation_machine_capability(
        tenant_id="t1",
        project_id="p1",
        machine={
            "machine_id": "m1",
            "machine_type": "center_pivot",
            "certification_status": "certified",
            "effective_area_ha": 50.0,
            "design_flow_lps": 50.0,
            "full_cycle_hours": 10.0,
            "minimum_speed_percent": 20.0,
            "maximum_speed_percent": 100.0,
            "required_inlet_pressure_bar": 2.0,
        },
        hydraulic_capability={
            "status": "verified",
            "operational_eligible": True,
            "maximum_deliverable_flow_lps": 40.0,
            "terminal_pressure_bar": 2.5,
        },
        controller={"certification_status": "certified", "capabilities": {"read_status": True}},
    )
    assert out.status == "blocked"
    assert "INSUFFICIENT_HYDRAULIC_FLOW_FOR_MACHINE" in out.blocking_reasons


pytestmark = pytest.mark.unit
