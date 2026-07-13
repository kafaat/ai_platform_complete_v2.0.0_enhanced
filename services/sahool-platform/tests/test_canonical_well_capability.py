from __future__ import annotations

from datetime import UTC, datetime, timedelta

from api.canonical_well_capability import (
    build_canonical_well_capability,
    well_capability_to_mpc_constraints,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _inputs() -> dict:
    return {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "water_source": {
            "id": "source-1",
            "commissioned_max_flow_lps": 50.0,
            "maximum_allowed_ec_ds_m": 3.0,
            "evidence": {"commissioning": "ev-source"},
        },
        "well": {
            "id": "well-1",
            "water_source_id": "source-1",
            "sustainable_flow_lps": 44.0,
            "maximum_drawdown_m": 20.0,
            "minimum_rest_hours": 2.0,
            "evidence": {"construction": "ev-well"},
        },
        "pumping_test": {
            "id": "test-1",
            "status": "certified",
            "tested_at": (NOW - timedelta(days=30)).isoformat(),
            "tested_flow_lps": 48.0,
            "recommended_sustainable_flow_lps": 42.0,
            "recovery_rate_m_h": 5.0,
        },
        "latest_measurement": {
            "id": "measurement-1",
            "measured_at": (NOW - timedelta(hours=2)).isoformat(),
            "static_level_m": 30.0,
            "dynamic_level_m": 40.0,
        },
        "allocation": {
            "id": "allocation-1",
            "daily_allocation_m3": 4000.0,
            "daily_used_m3": 1000.0,
            "seasonal_allocation_m3": 100000.0,
            "seasonal_used_m3": 20000.0,
        },
        "water_quality": {
            "id": "quality-1",
            "sampled_at": (NOW - timedelta(days=20)).isoformat(),
            "ec_ds_m": 1.8,
        },
        "now": NOW,
    }


def test_builds_verified_capability_and_uses_weakest_flow_limit() -> None:
    capability = build_canonical_well_capability(**_inputs())
    assert capability.status == "verified"
    assert capability.operational_eligible is True
    # Allocation: 3000 m3 / 86400 s = 34.7222 L/s, lower than the certified 42 L/s.
    assert round(capability.maximum_flow_lps, 4) == 34.7222
    assert capability.drawdown_m == 10.0
    assert capability.specific_capacity_lps_per_m == 4.8
    assert len(capability.capability_digest) == 64


def test_missing_certified_test_fails_closed() -> None:
    values = _inputs()
    values["pumping_test"]["status"] = "reviewed"
    result = build_canonical_well_capability(**values)
    assert result == {"status": "blocked", "reason": "certified_pumping_test_required"}


def test_stale_measurement_blocks_operation() -> None:
    values = _inputs()
    values["latest_measurement"]["measured_at"] = (NOW - timedelta(hours=30)).isoformat()
    capability = build_canonical_well_capability(**values)
    assert capability.status == "blocked"
    assert "WELL_MEASUREMENT_STALE" in capability.blocking_reasons


def test_salinity_limit_blocks_operation() -> None:
    values = _inputs()
    values["water_quality"]["ec_ds_m"] = 4.2
    capability = build_canonical_well_capability(**values)
    assert "WATER_SALINITY_LIMIT_EXCEEDED" in capability.blocking_reasons


def test_digest_changes_when_allocation_changes() -> None:
    first = build_canonical_well_capability(**_inputs())
    values = _inputs()
    values["allocation"]["daily_used_m3"] = 1200.0
    second = build_canonical_well_capability(**values)
    assert first.capability_digest != second.capability_digest


def test_mpc_adapter_is_fail_closed_and_carries_digest() -> None:
    capability = build_canonical_well_capability(**_inputs())
    constraints = well_capability_to_mpc_constraints(capability)
    assert constraints["status"] == "available"
    assert constraints["source_well_id"] == "well-1"
    assert constraints["well_capability_digest"] == capability.capability_digest

    blocked = well_capability_to_mpc_constraints({"status": "blocked", "reason": "missing"})
    assert blocked["status"] == "blocked"
