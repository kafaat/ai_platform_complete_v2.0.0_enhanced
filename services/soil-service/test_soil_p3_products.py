from datetime import UTC, datetime

from p3_products import (
    build_analog_field_product,
    build_drainage_assessment,
    build_mobile_visual_observation,
    build_reclamation_assessment,
    build_reclamation_economics,
)

from shared.contracts.soil.p3 import (
    AnalogFieldCandidate,
    AnalogFieldRequest,
    DrainageAssessmentRequest,
    MobileImageQuality,
    MobileSoilImageRequest,
    ReclamationAssessmentRequest,
    ReclamationEconomicsRequest,
    SoilVisualPrediction,
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
