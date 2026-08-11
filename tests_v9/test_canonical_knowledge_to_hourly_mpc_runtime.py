from datetime import UTC, datetime, timedelta

import pytest
from api.canonical_irrigation_capability_graph import build_canonical_irrigation_capability_graph
from api.canonical_root_zone_profile import build_canonical_root_zone_profile
from api.canonical_sprinkler_runoff_capability import build_canonical_sprinkler_runoff_capability
from api.hourly_energy_aware_irrigation_mpc import solve_hourly_energy_aware_mpc

pytestmark = pytest.mark.unit


def _hv(value, unit="m3/m3"):
    return {"value": value, "unit": unit, "origin": "measured", "confidence": 0.95}


def _root(raw_fraction: float):
    soil = {
        "profile_id": "soil-profile-1",
        "tenant_id": "tenant-1",
        "field_id": "field-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "executable": True,
        "source_soil_profile_hash": "soil-hash-1",
        "layers": [
            {
                "depth_from_cm": 0,
                "depth_to_cm": 100,
                "field_capacity": _hv(0.30),
                "wilting_point": _hv(0.12),
                "coarse_fragments": _hv(10.0, "%"),
                "infiltration": _hv(15.0, "mm/h"),
                "ksat": _hv(20.0, "mm/h"),
            }
        ],
    }
    policy = {
        "policy_id": "11111111-1111-1111-1111-111111111111",
        "initial_depth_m": 0.2,
        "maximum_depth_m": 1.0,
        "effective_fraction": 0.8,
        "policy_version": "maize-roots.v1",
        "evidence_ids": ["evidence-1"],
    }
    out = build_canonical_root_zone_profile(
        tenant_id="tenant-1",
        field_id="field-1",
        season_id="season-1",
        crop="maize",
        phenology_progress=0.5,
        raw_fraction=raw_fraction,
        root_policy=policy,
        soil_profile=soil,
    )
    assert not isinstance(out, dict)
    return out.to_dict()


def _sprinkler(root):
    out = build_canonical_sprinkler_runoff_capability(
        tenant_id="tenant-1",
        project_id="project-1",
        machine_capability={
            "status": "verified",
            "operational_eligible": True,
            "machine_id": "machine-1",
            "capability_digest": "1" * 64,
        },
        package={
            "package_id": "sprinkler-1",
            "certification_status": "certified",
            "tested_peak_application_mm_h": 9.0,
            "test_quality": "certified",
            "test_digest": "2" * 64,
        },
        root_zone_profile=root,
        terrain={
            "maximum_slope_percent": 2.0,
            "quality": "certified",
            "profile_digest": "3" * 64,
        },
        weather={
            "wind_speed_m_s": 2.0,
            "quality": "measured",
            "snapshot_digest": "4" * 64,
        },
    )
    assert not isinstance(out, dict)
    assert out.status == "verified"
    return out


def _graph(sprinkler):
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    graph = build_canonical_irrigation_capability_graph(
        tenant_id="tenant-1",
        project_id="project-1",
        field_id="field-1",
        season_id="season-1",
        well_capability={
            "status": "verified",
            "operational_eligible": True,
            "well_id": "well-1",
            "maximum_flow_lps": 50.0,
            "maximum_daily_volume_m3": 4000.0,
            "remaining_daily_volume_m3": 3200.0,
            "remaining_seasonal_volume_m3": 80000.0,
            "minimum_rest_hours": 0.0,
            "capability_digest": "5" * 64,
            "limitations": [],
        },
        hydraulic_capability={
            "status": "verified",
            "operational_eligible": True,
            "well_id": "well-1",
            "pump_id": "pump-1",
            "target_asset_id": "machine-1",
            "maximum_deliverable_flow_lps": 42.0,
            "terminal_pressure_bar": 2.5,
            "electrical_power_kw": 48.0,
            "specific_energy_kwh_m3": 0.32,
            "capability_digest": "6" * 64,
            "limitations": [],
        },
        machine_capability={
            "status": "verified",
            "operational_eligible": True,
            "machine_id": "machine-1",
            "design_flow_lps": 45.0,
            "maximum_daily_depth_mm": 18.0,
            "capability_digest": "7" * 64,
            "limitations": [],
        },
        sprinkler_capability=sprinkler,
        energy_capability={
            "status": "verified",
            "operational_eligible": True,
            "energy_system_id": "energy-1",
            "hourly_envelopes": [
                {
                    "hour": (now + timedelta(hours=i)).isoformat(),
                    "maximum_continuous_load_kw": 100.0,
                    "maximum_starting_kva": 150.0,
                    "permitted_load_ids": ["pump"],
                    "energy_cost_per_kwh": 0.1,
                    "renewable_fraction": 0.8,
                }
                for i in range(8)
            ],
            "capability_digest": "8" * 64,
            "limitations": [],
        },
        controller={
            "controller_id": "controller-1",
            "machine_id": "machine-1",
            "certification_status": "certified",
            "connection_status": "online",
            "telemetry_fresh": True,
            "capabilities": {"read_status": True, "read_position": True, "start_stop": True},
            "capability_digest": "9" * 64,
        },
        required_energy_load_ids=["pump"],
    )
    assert graph.status == "verified"
    payload = graph.to_dict()
    payload["irrigation_capability_digest"] = graph.capability_digest
    payload["pump_starting_kva"] = 60.0
    payload["required_energy_load_ids"] = ["pump"]
    return payload


def _solve(graph):
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    hours = [
        {
            "hour": (now + timedelta(hours=i)).isoformat(),
            "etc_mm": 0.5,
            "effective_rain_mm": 0.0,
            "maximum_available_power_kw": 100.0,
            "maximum_starting_kva": 150.0,
            "energy_cost_per_kwh": 0.1,
            "renewable_fraction": 0.8,
            "permitted_load_ids": ["pump"],
            "energy_window_digest": f"{i:064x}"[-64:],
        }
        for i in range(8)
    ]
    return solve_hourly_energy_aware_mpc(
        tenant_id="tenant-1",
        field_id="field-1",
        season_id="season-1",
        canonical_water_state={
            "operational_eligible": True,
            "taw_mm": 100.0,
            "raw_mm": 50.0,
            "depletion_mm": 80.0,
            "water_state_digest": "b" * 64,
            "weather_snapshot_digest": "c" * 64,
            "soil_profile_digest": "d" * 64,
            "season_state_digest": "e" * 64,
        },
        irrigation_capability=graph,
        commissioning_gate={
            "status": "executable",
            "execution_allowed": True,
            "executability_digest": "f" * 64,
        },
        hourly_forecast=hours,
        area_ha=1.0,
        maximum_horizon_hours=8,
        minimum_runtime_minutes=1.0,
        minimum_off_hours=0,
    )


def test_canonical_root_zone_limit_changes_actual_hourly_mpc_action():
    low_root = _root(0.12)
    high_root = _root(0.50)

    low_sprinkler = _sprinkler(low_root)
    high_sprinkler = _sprinkler(high_root)

    assert low_sprinkler.maximum_safe_depth_mm_event == pytest.approx(
        low_root["root_zone_refill_cap_mm"]
    )
    assert high_sprinkler.maximum_safe_depth_mm_event == pytest.approx(
        high_root["root_zone_refill_cap_mm"]
    )
    assert low_sprinkler.maximum_safe_depth_mm_event < high_sprinkler.maximum_safe_depth_mm_event

    low_graph = _graph(low_sprinkler)
    high_graph = _graph(high_sprinkler)
    assert low_graph["maximum_safe_depth_mm_event"] < high_graph["maximum_safe_depth_mm_event"]

    low_schedule = _solve(low_graph)
    high_schedule = _solve(high_graph)

    assert low_schedule.actions
    assert high_schedule.actions
    low_first = low_schedule.actions[0]["irrigation_depth_mm"]
    high_first = high_schedule.actions[0]["irrigation_depth_mm"]

    assert low_first <= low_graph["maximum_safe_depth_mm_event"] + 1e-9
    assert high_first <= high_graph["maximum_safe_depth_mm_event"] + 1e-9
    assert low_first < high_first


def test_m3_fails_closed_when_engineering_event_limit_is_removed():
    graph = _graph(_sprinkler(_root(0.50)))
    graph.pop("maximum_safe_depth_mm_event")
    schedule = _solve(graph)
    assert schedule.status == "blocked"
    assert "COMPLETE_ENGINEERING_CAPABILITY_REQUIRED" in schedule.blocking_reasons
