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


def test_preserves_hydraulic_measurements_while_abstraction_is_unverified() -> None:
    capability = build_canonical_well_capability(**_with_aquifer(sustainable_abstraction_lps=45.0))
    assert capability.status == "blocked"
    assert capability.remaining_daily_volume_m3 == 3000
    assert capability.well_hydraulic_flow_lps == 42
    assert capability.maximum_flow_lps == 0
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


def test_mpc_adapter_rejects_older_verified_snapshots() -> None:
    capability = build_canonical_well_capability(**_with_aquifer()).to_dict()
    capability.update(status="verified", operational_eligible=True, maximum_flow_lps=30.0)
    constraints = well_capability_to_mpc_constraints(capability)
    assert constraints["status"] == "blocked"
    assert constraints["blocking_reasons"] == ["AQUIFER_ALLOCATION_UNVERIFIED"]

    blocked = well_capability_to_mpc_constraints({"status": "blocked", "reason": "missing"})
    assert blocked["status"] == "blocked"


# ───────── P1: pumping test alone never proves sustainable aquifer abstraction ─────────


def _aquifer(**over) -> dict:
    ev = {
        "evidence_id": "aq-ev-1",
        "water_source_id": "source-1",
        "tenant_id": "tenant-1",
        "aquifer_id": "aquifer-1",
        "status": "certified",
        "basis": "hydrogeological_assessment",
        "issuer": "regulator-x",
        "assessed_at": (NOW - timedelta(days=100)).isoformat(),
        "valid_until": (NOW + timedelta(days=100)).isoformat(),
        "sustainable_abstraction_lps": 30.0,
    }
    ev.update(over)
    return ev


def _with_aquifer(**over) -> dict:
    values = _inputs()
    values["water_source"]["evidence"]["aquifer_safe_yield"] = _aquifer(**over)
    return values


def test_pumping_test_alone_is_not_operational_eligible() -> None:
    capability = build_canonical_well_capability(**_inputs())
    assert capability.operational_eligible is False
    assert capability.status == "blocked"
    assert "AQUIFER_SAFE_YIELD_EVIDENCE_REQUIRED" in capability.blocking_reasons
    assert well_capability_to_mpc_constraints(capability)["status"] == "blocked"


def test_source_report_preserves_the_shared_claim_without_authorizing_abstraction() -> None:
    capability = build_canonical_well_capability(**_with_aquifer())
    assert capability.operational_eligible is False
    assert capability.evidence["reported_aquifer_ceiling_lps"] == 30.0
    assert capability.aquifer_safe_yield_lps is None
    assert capability.maximum_flow_lps == 0.0
    assert capability.well_hydraulic_flow_lps == 42.0
    assert capability.evidence["aquifer_safe_yield_evidence_id"] == "aq-ev-1"


def test_aquifer_evidence_failures_fail_closed() -> None:
    bad = {
        "scope_mismatch": {"water_source_id": "other-source"},
        "tenant_mismatch": {"tenant_id": "other-tenant"},
        "uncertified": {"status": "draft"},
        "expired": {"valid_until": (NOW - timedelta(days=1)).isoformat()},
        "no_expiry": {"valid_until": None},
        "zero": {"sustainable_abstraction_lps": 0},
        "bool": {"sustainable_abstraction_lps": True},
        "no_id": {"evidence_id": ""},
        "no_issuer": {"issuer": ""},
        "no_aquifer": {"aquifer_id": ""},
    }
    for name, over in bad.items():
        cap = build_canonical_well_capability(**_with_aquifer(**over))
        assert cap.operational_eligible is False, name
        assert "AQUIFER_SAFE_YIELD_EVIDENCE_INVALID" in cap.blocking_reasons, name


def test_pumping_test_flow_in_well_evidence_is_not_accepted_as_aquifer_evidence() -> None:
    values = _inputs()
    values["well"]["evidence"]["aquifer_safe_yield"] = _aquifer()
    cap = build_canonical_well_capability(**values)
    assert cap.operational_eligible is False


def test_malformed_jsonb_never_raises_or_authorizes_a_well():
    from api.canonical_well_capability import evaluate_aquifer_safe_yield_evidence

    for malformed in (["not-an-object"], [], True, 3, "text", {"aquifer_safe_yield": []}):
        result = evaluate_aquifer_safe_yield_evidence(
            water_source={"evidence": malformed},
            tenant_id="tenant-1",
            water_source_id="source-1",
            now=NOW,
        )
        assert result["limit_lps"] is None
        assert result["blockers"] == ["AQUIFER_SAFE_YIELD_EVIDENCE_INVALID"]


def test_six_wells_cannot_each_claim_the_shared_abstraction_limit():
    for index in range(6):
        source = f"source-{index}"
        inputs = _with_aquifer(water_source_id=source)
        inputs["water_source"]["id"] = source
        inputs["well"].update(id=f"well-{index}", water_source_id=source)
        cap = build_canonical_well_capability(**inputs)
        assert cap.operational_eligible is False
        assert cap.maximum_flow_lps == 0.0
        assert "AQUIFER_ALLOCATION_UNVERIFIED" in cap.blocking_reasons
        assert cap.well_hydraulic_flow_lps == 42.0
