from datetime import UTC, datetime

import pytest
from p3_products import (
    _DRAINAGE_RISK_WEIGHTS,
    DrainageNeedConflict,
    build_analog_field_product,
    build_drainage_assessment,
    build_mobile_visual_observation,
    build_reclamation_assessment,
    build_reclamation_economics,
    reconcile_reclamation_drainage_need,
)

from shared.contracts.soil.p3 import (
    AnalogFieldCandidate,
    AnalogFieldRequest,
    DrainageAssessmentProduct,
    DrainageAssessmentRequest,
    MobileImageQuality,
    MobileSoilImageRequest,
    ReclamationAssessmentRequest,
    ReclamationEconomicsRequest,
    SoilVisualPrediction,
    p3_drainage_need_to_salinity_class,
)


def test_mobile_image_fail_closed_without_reference_card():
    req = MobileSoilImageRequest(
        tenant_id="t",
        field_id="f",
        object_uri="s3://bucket/a.jpg",
        captured_at=datetime.now(UTC),
        latitude=15,
        longitude=44,
        depth_cm=0,
        surface_moisture_state="dry",
        quality=MobileImageQuality(
            blur_score=0.9,
            exposure_score=0.9,
            shadow_fraction=0.1,
            reference_card_detected=False,
            scale_marker_detected=True,
            gps_accuracy_m=4,
        ),
        prediction=SoilVisualPrediction(
            salt_crust_probability=0.8,
            surface_crack_probability=0.1,
            coarse_fragment_probability=0.2,
            waterlogging_probability=0.1,
            segmentation_confidence=0.9,
        ),
    )
    out = build_mobile_visual_observation(req)
    assert not out.quality_gate_passed
    assert out.accepted_predictions == {}
    assert "gypsum_rate" in out.blocked_use


def test_analog_engine_anonymizes_and_blocks_high_risk():
    candidates = []
    for i, val in enumerate([30, 32, 28, 31]):
        candidates.append(
            AnalogFieldCandidate(
                field_id=f"secret-{i}",
                terrain={"slope": 1 + i * 0.01},
                trusted_properties={"clay_pct": val},
                evidence_quality=0.9,
            )
        )
    req = AnalogFieldRequest(
        tenant_id="t",
        field_id="f",
        target_features={"terrain": {"slope": 1}},
        candidates=candidates,
        requested_properties=["clay_pct"],
    )
    out = build_analog_field_product(req)
    assert out.estimates[0].status == "estimated"
    assert all("secret" not in str(x) for x in out.anonymized_cohort)
    assert "reclamation_execution" in out.blocked_use


def test_drainage_assessment_blocks_engineering_without_survey():
    req = DrainageAssessmentRequest(
        tenant_id="t",
        field_id="f",
        geometry_hash="g",
        natural_outlet_score=0.2,
        water_table_depth_m=0.5,
        impermeable_layer_depth_m=0.6,
        depression_fraction=0.4,
        mean_drainage_gradient_pct=0.1,
        ksat_mm_h=None,
        flood_risk=0.7,
        wadi_risk=0.6,
        salinity_persistence=0.8,
        surveyed_elevations=False,
    )
    out = build_drainage_assessment(req)
    assert out.drainage_need in {"combined", "surface", "subsurface"}
    assert "subsurface_drainage_design" in out.blocked_actions


def test_reclamation_fail_closed_then_unblocks_when_verified():
    base = dict(
        tenant_id="t",
        field_id="f",
        geometry_hash="g",
        salinity_probability=0.7,
        sodicity_probability=0.7,
        gypsum_probability=0.5,
        stoniness_fraction=0.1,
        compaction_risk=0.4,
        leveling_need=0.5,
        drainage_need="combined",
        crop_suitability_score=0.5,
        ec_lab_ds_m=8,
        esp_pct=18,
    )
    blocked = build_reclamation_assessment(ReclamationAssessmentRequest(**base))
    assert "reclamation_execution" in blocked.blocked_actions
    ready = build_reclamation_assessment(
        ReclamationAssessmentRequest(
            **base,
            lab_verified=True,
            irrigation_water_profile_approved=True,
            drainage_engineering_verified=True,
        )
    )
    assert "reclamation_execution" in ready.allowed_actions


def test_reclamation_economics_has_three_scenarios_and_risk_adjustment():
    req = ReclamationEconomicsRequest(
        tenant_id="t",
        field_id="f",
        area_ha=100,
        water_cost_per_m3=0.1,
        energy_cost_per_kwh=0.2,
        gypsum_cost_per_tonne=120,
        drainage_cost_per_ha=1000,
        leveling_cost_per_ha=300,
        stone_removal_cost_per_ha=200,
        expected_annual_margin_per_ha=800,
        water_m3_per_ha=300,
        energy_kwh_per_ha=150,
        gypsum_t_per_ha=2,
        drainage_required=True,
        leveling_required=True,
    )
    out = build_reclamation_economics(req)
    assert [s.name for s in out.scenarios] == ["minimum", "balanced", "full"]
    assert all(
        s.risk_adjusted_npv <= s.npv if s.npv >= 0 else s.risk_adjusted_npv >= s.npv
        for s in out.scenarios
    )


# --- drainage assessment: outlet term, unknown-hydrology priors, monotonicity ---

_GRID = [i / 10 for i in range(11)]


def _drainage_req(**overrides):
    base = dict(
        tenant_id="t",
        field_id="f",
        geometry_hash="g",
        natural_outlet_score=0.5,
        water_table_depth_m=1.5,
        impermeable_layer_depth_m=1.0,
        depression_fraction=0.1,
        mean_drainage_gradient_pct=0.3,
        ksat_mm_h=6.0,
        flood_risk=0.2,
        wadi_risk=0.2,
        salinity_persistence=0.2,
        surveyed_elevations=True,
    )
    base.update(overrides)
    return DrainageAssessmentRequest(**base)


def test_drainage_risk_weights_sum_to_one_and_include_outlet():
    assert _DRAINAGE_RISK_WEIGHTS["outlet"] > 0
    assert sum(_DRAINAGE_RISK_WEIGHTS.values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"water_table_depth_m": None, "impermeable_layer_depth_m": None, "ksat_mm_h": None},
        {"water_table_depth_m": 0.2, "depression_fraction": 0.9, "flood_risk": 1.0},
        {"depression_fraction": 1.0, "flood_risk": 1.0, "wadi_risk": 1.0},
    ],
)
def test_waterlogging_risk_strictly_decreases_as_outlet_improves(context):
    risks = [
        build_drainage_assessment(
            _drainage_req(natural_outlet_score=o, **context)
        ).waterlogging_risk
        for o in _GRID
    ]
    assert all(a > b for a, b in zip(risks, risks[1:], strict=False)), risks


@pytest.mark.parametrize("factor", ["flood_risk", "wadi_risk", "depression_fraction"])
@pytest.mark.parametrize("outlet", [0.0, 0.5, 1.0])
def test_waterlogging_risk_strictly_increases_with_hazard(factor, outlet):
    risks = [
        build_drainage_assessment(
            _drainage_req(natural_outlet_score=outlet, **{factor: v})
        ).waterlogging_risk
        for v in _GRID
    ]
    assert all(a < b for a, b in zip(risks, risks[1:], strict=False)), risks


def test_poor_outlet_triggers_surface_drainage_with_moderate_ponding():
    kwargs = dict(depression_fraction=0.15, flood_risk=0.4)
    good = build_drainage_assessment(_drainage_req(natural_outlet_score=0.9, **kwargs))
    poor = build_drainage_assessment(_drainage_req(natural_outlet_score=0.1, **kwargs))
    assert good.drainage_need in {"none", "monitor"}
    assert poor.drainage_need in {"surface", "combined"}
    assert any("outlet" in r for r in poor.recommendations)


def test_unknown_water_table_is_not_zero_risk():
    known_deep = build_drainage_assessment(_drainage_req(water_table_depth_m=5.0))
    unknown = build_drainage_assessment(_drainage_req(water_table_depth_m=None))
    assert unknown.waterlogging_risk > known_deep.waterlogging_risk
    unknown_layer = build_drainage_assessment(_drainage_req(impermeable_layer_depth_m=None))
    deep_layer = build_drainage_assessment(_drainage_req(impermeable_layer_depth_m=5.0))
    assert unknown_layer.waterlogging_risk > deep_layer.waterlogging_risk


def test_unknown_depths_do_not_assert_subsurface_need():
    out = build_drainage_assessment(
        _drainage_req(water_table_depth_m=None, impermeable_layer_depth_m=None)
    )
    assert out.drainage_need not in {"subsurface", "combined"}


@pytest.mark.parametrize("outlet", _GRID)
@pytest.mark.parametrize("ksat", [None, 50.0])
def test_all_unknown_hydrology_never_yields_none(outlet, ksat):
    out = build_drainage_assessment(
        _drainage_req(
            natural_outlet_score=outlet,
            water_table_depth_m=None,
            impermeable_layer_depth_m=None,
            ksat_mm_h=ksat,
            depression_fraction=0.0,
            mean_drainage_gradient_pct=5.0,
            flood_risk=0.0,
            wadi_risk=0.0,
            salinity_persistence=0.0,
        )
    )
    assert out.drainage_need != "none"
    assert "water_table_depth_unknown" in out.limitations
    assert "seasonal_water_table_monitoring" in out.prerequisites


def test_low_risk_with_measured_hydrology_can_still_be_none():
    out = build_drainage_assessment(
        _drainage_req(
            natural_outlet_score=1.0,
            water_table_depth_m=5.0,
            impermeable_layer_depth_m=5.0,
            ksat_mm_h=50.0,
            depression_fraction=0.0,
            mean_drainage_gradient_pct=5.0,
            flood_risk=0.0,
            wadi_risk=0.0,
            salinity_persistence=0.0,
        )
    )
    assert out.drainage_need == "none"
    assert out.limitations == []


# --- reclamation: drainage_need must agree with the stored assessment ---


def test_reclamation_drainage_need_conflict_with_stored_assessment():
    with pytest.raises(DrainageNeedConflict):
        reconcile_reclamation_drainage_need("none", {"drainage_need": "combined"})


def test_reclamation_drainage_need_matching_stored_assessment():
    prov = reconcile_reclamation_drainage_need(
        "surface", {"drainage_need": "surface", "product_id": "dap_1"}
    )
    assert prov["drainage_need_source"] == "stored_drainage_assessment"
    assert prov["drainage_assessment_product_id"] == "dap_1"
    assert prov["limitations"] == []


def test_reclamation_drainage_need_without_stored_assessment_is_flagged():
    prov = reconcile_reclamation_drainage_need("none", None)
    assert prov["drainage_need_source"] == "caller_asserted"
    assert prov["limitations"] == ["drainage_need_not_backed_by_stored_assessment"]


# --- P3 drainage_need -> salinity drainage vocabulary ---


@pytest.mark.parametrize(
    ("need", "limitations", "expected"),
    [
        ("none", [], "good"),
        ("monitor", [], "moderate"),
        ("surface", [], "poor"),
        ("subsurface", [], "poor"),
        ("combined", [], "poor"),
        ("monitor", ["water_table_depth_unknown"], "unknown"),
        ("none", ["water_table_depth_unknown"], "unknown"),
        ("combined", ["water_table_depth_unknown"], "poor"),
        (None, [], "unknown"),
        ("bogus", [], "unknown"),
    ],
)
def test_p3_drainage_need_to_salinity_class(need, limitations, expected):
    assert p3_drainage_need_to_salinity_class(need, limitations) == expected


def test_stored_payload_without_limitations_still_validates():
    payload = build_drainage_assessment(_drainage_req()).model_dump(mode="json")
    payload.pop("limitations")
    assert DrainageAssessmentProduct.model_validate(payload).limitations == []
