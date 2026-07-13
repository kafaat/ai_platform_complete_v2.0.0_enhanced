import pytest
from api.canonical_energy_microgrid_capability import (
    build_canonical_energy_microgrid_capability,
    energy_capability_to_mpc_constraints,
)


def _system():
    return {
        "energy_system_id": "energy-1",
        "certification_status": "certified",
        "quality": "field_validated",
        "pv_capacity_kwp": 100.0,
        "inverter_continuous_kw": 80.0,
        "inverter_peak_kva": 120.0,
        "pv_system_derate": 0.82,
        "pv_temperature_coefficient_per_c": -0.004,
        "evidence_digest": "a" * 64,
    }


def _battery(**overrides):
    data = {
        "chemistry": "lifepo4",
        "soc_percent": 70.0,
        "state_of_health_percent": 95.0,
        "usable_energy_kwh": 160.0,
        "maximum_charge_kw": 50.0,
        "maximum_discharge_kw": 40.0,
        "minimum_soc_percent": 15.0,
        "emergency_reserve_percent": 20.0,
        "temperature_c": 28.0,
        "bms_status": "ready",
        "evidence_digest": "b" * 64,
    }
    data.update(overrides)
    return data


def _loads():
    return [
        {
            "load_id": "main-pump",
            "load_type": "main_pump",
            "rated_kw": 45.0,
            "starting_kva": 70.0,
            "priority": 2,
            "certification_status": "certified",
            "evidence_digest": "c" * 64,
        },
        {
            "load_id": "pivot-1",
            "load_type": "pivot_drive",
            "rated_kw": 8.0,
            "starting_kva": 20.0,
            "priority": 3,
            "certification_status": "certified",
            "evidence_digest": "d" * 64,
        },
    ]


def _weather():
    return [
        {
            "hour": "2026-07-13T10:00:00Z",
            "solar_radiation_w_m2": 850.0,
            "temperature_c": 32.0,
            "quality": "forecast",
            "snapshot_digest": "e" * 64,
        },
        {
            "hour": "2026-07-13T20:00:00Z",
            "solar_radiation_w_m2": 0.0,
            "temperature_c": 25.0,
            "quality": "forecast",
            "snapshot_digest": "f" * 64,
        },
    ]


def test_builds_verified_hourly_energy_capability():
    out = build_canonical_energy_microgrid_capability(
        tenant_id="t1",
        project_id="p1",
        system=_system(),
        battery=_battery(),
        generator={
            "available": True,
            "continuous_kw": 30.0,
            "starting_kva": 80.0,
            "energy_cost_per_kwh": 0.4,
            "certification_status": "certified",
            "evidence_digest": "1" * 64,
        },
        grid=None,
        loads=_loads(),
        weather_hours=_weather(),
    )
    assert out.status == "verified"
    assert out.operational_eligible is True
    assert len(out.hourly_envelopes) == 2
    assert out.hourly_envelopes[0]["pv_available_kw"] > 0
    assert "main-pump" in out.hourly_envelopes[0]["permitted_load_ids"]
    assert len(out.capability_digest) == 64
    constraints = energy_capability_to_mpc_constraints(out)
    assert constraints["status"] == "available"
    assert len(constraints["energy_capability_digest"]) == 64


def test_protects_battery_reserve():
    out = build_canonical_energy_microgrid_capability(
        tenant_id="t1",
        project_id="p1",
        system=_system(),
        battery=_battery(soc_percent=20.0),
        generator=None,
        grid=None,
        loads=_loads(),
        weather_hours=_weather(),
    )
    assert out.status == "verified"
    assert out.hourly_envelopes[1]["battery_discharge_limit_kw"] == 0.0
    assert "battery reserve protected; discharge unavailable" in out.limitations


def test_blocks_bad_bms():
    out = build_canonical_energy_microgrid_capability(
        tenant_id="t1",
        project_id="p1",
        system=_system(),
        battery=_battery(bms_status="fault"),
        generator=None,
        grid=None,
        loads=_loads(),
        weather_hours=_weather(),
    )
    assert out.status == "blocked"
    assert "BATTERY_BMS_NOT_READY" in out.blocking_reasons


def test_blocks_starting_kva_above_available_source():
    loads = _loads()
    loads[0]["starting_kva"] = 200.0
    out = build_canonical_energy_microgrid_capability(
        tenant_id="t1",
        project_id="p1",
        system=_system(),
        battery=_battery(),
        generator=None,
        grid=None,
        loads=loads,
        weather_hours=_weather(),
    )
    assert out.status == "verified"
    assert out.hourly_envelopes[0]["blocked_loads"][0]["reason"] == "STARTING_KVA_LIMIT_EXCEEDED"


def test_blocks_grid_voltage_and_frequency_outside_limits():
    out = build_canonical_energy_microgrid_capability(
        tenant_id="t1",
        project_id="p1",
        system=_system(),
        battery=None,
        generator=None,
        grid={
            "available": True,
            "contracted_kw": 100.0,
            "starting_kva": 150.0,
            "voltage_within_limits": False,
            "frequency_within_limits": False,
            "energy_cost_per_kwh": 0.1,
            "evidence_digest": "2" * 64,
        },
        loads=_loads(),
        weather_hours=_weather(),
    )
    assert out.status == "blocked"
    assert "GRID_VOLTAGE_OUT_OF_RANGE" in out.blocking_reasons
    assert "GRID_FREQUENCY_OUT_OF_RANGE" in out.blocking_reasons


def test_requires_certified_load_profiles():
    loads = _loads()
    loads[0]["certification_status"] = "draft"
    out = build_canonical_energy_microgrid_capability(
        tenant_id="t1",
        project_id="p1",
        system=_system(),
        battery=_battery(),
        generator=None,
        grid=None,
        loads=loads,
        weather_hours=_weather(),
    )
    assert out.status == "blocked"
    assert "CERTIFIED_LOAD_PROFILE_REQUIRED" in out.blocking_reasons


def test_digest_changes_when_weather_changes():
    first = build_canonical_energy_microgrid_capability(
        tenant_id="t1",
        project_id="p1",
        system=_system(),
        battery=_battery(),
        generator=None,
        grid=None,
        loads=_loads(),
        weather_hours=_weather(),
    )
    changed_weather = _weather()
    changed_weather[0]["solar_radiation_w_m2"] = 500.0
    second = build_canonical_energy_microgrid_capability(
        tenant_id="t1",
        project_id="p1",
        system=_system(),
        battery=_battery(),
        generator=None,
        grid=None,
        loads=_loads(),
        weather_hours=changed_weather,
    )
    assert first.capability_digest != second.capability_digest


pytestmark = pytest.mark.unit
