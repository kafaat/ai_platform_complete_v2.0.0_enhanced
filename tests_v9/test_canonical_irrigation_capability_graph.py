import pytest
from api.canonical_irrigation_capability_graph import (
    build_canonical_irrigation_capability_graph,
    irrigation_capability_graph_to_mpc_constraints,
)


def _well(**overrides):
    data = {
        "status": "verified",
        "operational_eligible": True,
        "well_id": "well-1",
        "maximum_flow_lps": 50.0,
        "maximum_daily_volume_m3": 4000.0,
        "remaining_daily_volume_m3": 3200.0,
        "remaining_seasonal_volume_m3": 80000.0,
        "minimum_rest_hours": 2.0,
        "capability_digest": "a" * 64,
        "limitations": [],
    }
    data.update(overrides)
    return data


def _hydraulic(**overrides):
    data = {
        "status": "verified",
        "operational_eligible": True,
        "well_id": "well-1",
        "pump_id": "pump-1",
        "target_asset_id": "machine-1",
        "maximum_deliverable_flow_lps": 42.0,
        "terminal_pressure_bar": 2.5,
        "electrical_power_kw": 48.0,
        "specific_energy_kwh_m3": 0.32,
        "capability_digest": "b" * 64,
        "limitations": [],
    }
    data.update(overrides)
    return data


def _machine(**overrides):
    data = {
        "status": "verified",
        "operational_eligible": True,
        "machine_id": "machine-1",
        "design_flow_lps": 45.0,
        "maximum_daily_depth_mm": 18.0,
        "capability_digest": "c" * 64,
        "limitations": [],
    }
    data.update(overrides)
    return data


def _sprinkler(**overrides):
    data = {
        "status": "verified",
        "operational_eligible": True,
        "machine_id": "machine-1",
        "maximum_safe_depth_mm_event": 12.0,
        "runoff_safety_factor": 1.25,
        "capability_digest": "d" * 64,
        "limitations": [],
    }
    data.update(overrides)
    return data


def _energy(**overrides):
    data = {
        "status": "verified",
        "operational_eligible": True,
        "energy_system_id": "energy-1",
        "hourly_envelopes": [
            {
                "hour": "2026-07-13T10:00:00Z",
                "maximum_continuous_load_kw": 90.0,
                "maximum_starting_kva": 120.0,
                "permitted_load_ids": ["main-pump", "pivot-1"],
                "energy_cost_per_kwh": 0.1,
                "renewable_fraction": 0.8,
            },
            {
                "hour": "2026-07-13T20:00:00Z",
                "maximum_continuous_load_kw": 20.0,
                "maximum_starting_kva": 35.0,
                "permitted_load_ids": ["pivot-1"],
                "energy_cost_per_kwh": 0.3,
                "renewable_fraction": 0.2,
            },
        ],
        "capability_digest": "e" * 64,
        "limitations": [],
    }
    data.update(overrides)
    return data


def _controller(**overrides):
    data = {
        "controller_id": "controller-1",
        "machine_id": "machine-1",
        "certification_status": "certified",
        "connection_status": "online",
        "telemetry_fresh": True,
        "capabilities": {
            "read_status": True,
            "read_position": True,
            "start_stop": True,
            "set_speed": True,
        },
        "capability_digest": "f" * 64,
    }
    data.update(overrides)
    return data


def _build(**overrides):
    args = {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "field_id": "field-1",
        "season_id": "season-1",
        "well_capability": _well(),
        "hydraulic_capability": _hydraulic(),
        "machine_capability": _machine(),
        "sprinkler_capability": _sprinkler(),
        "energy_capability": _energy(),
        "controller": _controller(),
        "required_energy_load_ids": ["main-pump", "pivot-1"],
    }
    args.update(overrides)
    return build_canonical_irrigation_capability_graph(**args)


def test_builds_verified_weakest_link_graph():
    graph = _build()
    assert graph.status == "verified"
    assert graph.operational_eligible is True
    assert graph.maximum_flow_lps == 42.0
    assert graph.maximum_safe_depth_mm_event == 12.0
    assert graph.weakest_link == "energy"
    assert len(graph.capability_digest) == 64
    assert [item["operational"] for item in graph.hourly_operating_windows] == [True, False]


def test_controller_telemetry_failure_blocks_entire_graph():
    graph = _build(controller=_controller(telemetry_fresh=False))
    assert graph.status == "blocked"
    assert graph.weakest_link == "controller"
    assert any("CONTROLLER_TELEMETRY_STALE" in item for item in graph.blocking_reasons)


def test_blocked_source_link_is_fail_closed():
    graph = _build(
        sprinkler_capability=_sprinkler(
            status="blocked",
            operational_eligible=False,
            blocking_reasons=["RUNOFF_RISK_HIGH"],
        )
    )
    assert graph.operational_eligible is False
    assert graph.weakest_link == "sprinkler"
    assert "SPRINKLER::RUNOFF_RISK_HIGH" in graph.blocking_reasons


def test_cross_link_identity_mismatch_blocks_graph():
    graph = _build(hydraulic_capability=_hydraulic(target_asset_id="other-machine"))
    assert graph.status == "blocked"
    assert "GRAPH_IDENTITY::HYDRAULIC_MACHINE_MISMATCH" in graph.blocking_reasons


def test_no_energy_window_blocks_graph():
    graph = _build(
        energy_capability=_energy(
            hourly_envelopes=[
                {
                    "hour": "2026-07-13T20:00:00Z",
                    "maximum_continuous_load_kw": 20.0,
                    "maximum_starting_kva": 30.0,
                    "permitted_load_ids": ["pivot-1"],
                    "energy_cost_per_kwh": 0.3,
                    "renewable_fraction": 0.2,
                }
            ]
        )
    )
    assert "GRAPH_ENERGY::NO_FEASIBLE_OPERATING_WINDOW" in graph.blocking_reasons


def test_digest_changes_when_any_link_changes():
    first = _build()
    second = _build(hydraulic_capability=_hydraulic(capability_digest="9" * 64))
    assert first.capability_digest != second.capability_digest


def test_mpc_boundary_exposes_only_verified_graph():
    graph = _build()
    constraints = irrigation_capability_graph_to_mpc_constraints(graph)
    assert constraints["status"] == "available"
    assert constraints["maximum_flow_lps"] == 42.0
    assert len(constraints["hourly_operating_windows"]) == 1
    blocked = irrigation_capability_graph_to_mpc_constraints(
        _build(controller=_controller(connection_status="offline"))
    )
    assert blocked["status"] == "blocked"
    assert blocked["weakest_link"] == "controller"


pytestmark = pytest.mark.unit
