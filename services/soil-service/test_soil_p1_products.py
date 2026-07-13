from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from p1_products import build_hydraulic_profile, build_sampling_plan, build_water_profile

from shared.contracts.soil import (
    IrrigationWaterSample,
    SamplingCandidate,
    SamplingPlanRequest,
    SoilProfileSnapshot,
)


def test_sampling_plan_zone_balance_and_exclusions():
    req = SamplingPlanRequest(
        tenant_id="t",
        field_id="f",
        mode="balanced",
        target_count=3,
        min_boundary_buffer_m=10,
        candidates=[
            SamplingCandidate(
                id="a", lon=1, lat=1, zone_id="z1", uncertainty=0.9, boundary_distance_m=20
            ),
            SamplingCandidate(
                id="b", lon=2, lat=2, zone_id="z1", uncertainty=0.8, boundary_distance_m=20
            ),
            SamplingCandidate(
                id="c",
                lon=3,
                lat=3,
                zone_id="z2",
                uncertainty=0.7,
                anomaly=0.9,
                boundary_distance_m=20,
            ),
            SamplingCandidate(
                id="d", lon=4, lat=4, zone_id="z2", uncertainty=0.9, boundary_distance_m=2
            ),
        ],
    )
    plan = build_sampling_plan(req)
    assert len(plan.points) == 3
    assert {p.zone_id for p in plan.points} == {"z1", "z2"}
    assert plan.excluded["boundary_buffer"] == 1


def _snapshot(props):
    now = datetime.now(UTC)
    layers = [
        {
            "depth_from_cm": 0,
            "depth_to_cm": 30,
            "properties": {
                k: {
                    "value": v,
                    "unit": None,
                    "evidence_class": "measured",
                    "selected_source": "laboratory",
                    "source_id": f"o_{k}",
                    "confidence": 0.95,
                }
                for k, v in props.items()
            },
        }
    ]
    payload = {
        "profile_id": "sp1",
        "profile_hash": "a" * 64,
        "tenant_id": "t",
        "field_id": "f",
        "effective_at": now,
        "data_available_at": now,
        "status": "verified",
        "evidence_level": "lab_verified",
        "layers": layers,
        "completeness_score": 1,
        "quality_gate": {"passed": True, "executable": False},
        "selection_policy_version": "v1",
    }
    return SoilProfileSnapshot.model_validate(payload)


def test_hydraulic_prefers_measured_and_labels_ptf():
    direct = build_hydraulic_profile(
        _snapshot({"field_capacity": 0.31, "wilting_point": 0.12, "bulk_density": 1.35})
    )
    assert direct.layers[0].field_capacity.origin == "measured"
    inferred = build_hydraulic_profile(
        _snapshot({"sand_pct": 55, "clay_pct": 20, "organic_matter": 1.5, "bulk_density": 1.4})
    )
    assert inferred.layers[0].field_capacity.origin == "pedotransfer"
    assert inferred.layers[0].available_water_capacity.value > 0


def test_water_profile_governance_and_indices():
    s = IrrigationWaterSample(
        sample_id="w1",
        tenant_id="t",
        field_id="f",
        source_id="well7",
        sampled_at=datetime.now(UTC),
        approved=True,
        ecw_ds_m=1.2,
        na_meq_l=8,
        ca_meq_l=4,
        mg_meq_l=2,
        hco3_meq_l=3,
        co3_meq_l=0,
    )
    p = build_water_profile(s)
    assert p.sar is not None and p.rsc_meq_l == -3
    assert "irrigation_planning" in p.allowed_use
    draft = build_water_profile(s.model_copy(update={"approved": False}))
    assert "reclamation_execution" in draft.blocked_use
