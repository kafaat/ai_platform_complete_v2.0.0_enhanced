import math

import pytest
from p3_products import build_drainage_assessment

from shared.contracts.soil.p3 import DrainageAssessmentRequest


def drainage_input():
    return dict(
        tenant_id="a",
        field_id="north",
        geometry_hash="g",
        natural_outlet_score=1,
        depression_fraction=0,
        mean_drainage_gradient_pct=1,
        flood_risk=0,
        wadi_risk=0,
        salinity_persistence=0,
    )


def test_fao_example_41_and_compaction_profile():
    d = drainage_input()
    d.update(
        spacing_scenario=dict(
            source_ref="FAO example 41",
            k_above_m_day=0.8,
            k_below_m_day=0.8,
            equivalent_depth_m=3.65,
            midpoint_head_m=0.6,
            recharge_mm_day=2,
        ),
        compaction_survey=dict(
            source_ref="field notebook",
            moisture_condition="field_capacity",
            reference_mpa=2,
            reference_source="local trial",
            samples=[dict(depth_cm=15, resistance_mpa=1.3), dict(depth_cm=30, resistance_mpa=2.4)],
        ),
    )
    p = build_drainage_assessment(DrainageAssessmentRequest(**d))
    assert p.provenance["spacing_scenario"]["spacing_m"] == pytest.approx(math.sqrt(7584))
    assert p.provenance["compaction_survey"]["exceeding_depths_cm"] == [30]
    assert p.provenance["engineering_design"] is False


def test_noncomparable_soil_moisture_withholds_threshold_comparison():
    d = drainage_input()
    d.update(
        compaction_survey=dict(
            source_ref="A",
            moisture_condition="unknown",
            reference_mpa=2,
            reference_source="local trial",
            samples=[dict(depth_cm=15, resistance_mpa=4)],
        )
    )
    p = build_drainage_assessment(DrainageAssessmentRequest(**d))
    assert p.provenance["compaction_survey"]["exceeding_depths_cm"] is None


def test_weighted_land_quality_is_profile_specific_and_withheld_if_incomplete():
    from shared.contracts.soil.drainage_design import LandQualityScenario

    common = dict(
        weight=0.5,
        unit="cm",
        method="field survey",
        observation_ref="survey",
        zero_score_at=0,
        full_score_at=100,
    )
    factors = [
        dict(**common, name="depth", observed=70),
        {
            **common,
            "name": "surface stones",
            "observed": 30,
            "zero_score_at": 100,
            "full_score_at": 0,
        },
    ]
    assert LandQualityScenario(profile_ref="test profile", factors=factors).assessment()[
        "weighted_index"
    ] == pytest.approx(0.7)
    factors[0]["observed"] = None
    assert (
        LandQualityScenario(profile_ref="test profile", factors=factors).assessment()[
            "weighted_index"
        ]
        is None
    )


def test_legacy_drainage_identity_omits_absent_or_null_scenario_keys():
    raw = drainage_input()
    before = DrainageAssessmentRequest(**raw).model_dump(mode="json")
    after = DrainageAssessmentRequest(
        **raw, spacing_scenario=None, compaction_survey=None
    ).model_dump(mode="json")
    assert before == after
    assert "spacing_scenario" not in after and "compaction_survey" not in after
