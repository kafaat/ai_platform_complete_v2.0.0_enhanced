from core.productivity_zones import (
    ProductivityObservation,
    build_daily_ai_brief,
    build_productivity_zones,
    classify_productivity_zone,
    generate_zone_sampling_plan,
)


def test_productivity_zone_classifies_problem_salinity_without_fabrication():
    obs = ProductivityObservation(
        id="a", area_ha=10, ndvi_mean=0.55, yield_rel=1.0, soil_ec_dsm=9.0
    )
    zone = classify_productivity_zone(obs)
    assert zone.zone_class == "problem"
    assert "ملوحة" in " ".join(zone.limiting_factors_ar)
    assert zone.sampling_priority == "high"


def test_build_productivity_zones_summary_area_and_confidence():
    out = build_productivity_zones(
        [
            ProductivityObservation(id="low", area_ha=4, ndvi_mean=0.30, yield_rel=0.75),
            ProductivityObservation(id="med", area_ha=6, ndvi_mean=0.48, yield_rel=1.0),
            ProductivityObservation(id="hi", area_ha=10, ndvi_mean=0.78, yield_rel=1.25),
        ]
    )
    assert out["total_area_ha"] == 20
    assert out["summary"]["high"]["area_pct"] == 50.0
    assert out["data_sufficiency"] == "sufficient"


def test_sampling_plan_uses_zone_priority_and_reports_unplaceable():
    out = generate_zone_sampling_plan(
        [
            ProductivityObservation(id="low", area_ha=2, ndvi_mean=0.28, lat=15.0, lng=44.0),
            ProductivityObservation(id="missing", area_ha=2, ndvi_mean=0.80),
        ]
    )
    assert out["count"] == 3
    assert out["sample_points"][0]["priority"] == "high"
    assert out["unplaceable_observation_ids"] == ["missing"]


def test_daily_ai_brief_prioritizes_actionable_signals():
    brief = build_daily_ai_brief(
        field_id="f1",
        signals={
            "ndvi_drop_pct": 14,
            "vpd_kpa": 2.8,
            "et0_mm_day": 6.5,
            "wind_speed_kmh": 24,
            "lab_recommendation_gate": "needs_review",
        },
        tasks=[{"status": "pending", "overdue": True}],
    )
    assert brief["is_grounded"] is True
    assert brief["actions"][0]["priority"] == "high"
    titles = " ".join(a["title_ar"] for a in brief["actions"])
    assert "NDVI" in brief["actions"][0]["reason_ar"] or "الغطاء النباتي" in titles
    assert "المختبر" in titles


def test_daily_ai_brief_accepts_common_aliases_and_lab_water_quality():
    brief = build_daily_ai_brief(
        field_id="f2",
        signals={
            "ndvi_delta_pct": 12,
            "vpd": 2.7,
            "et0": 6.1,
            "wind_speed": 21,
            "soil_ec": 5.2,
            "irrigation_water_ec": 3.1,
            "sar": 10.0,
        },
        tasks=[],
    )
    action_ids = {a["action_id"] for a in brief["actions"]}
    assert "inspect-ndvi-drop" in action_ids
    assert "salinity-zone-review" in action_ids
    assert "water-quality-watch" in action_ids
    assert brief["decision_policy"] == "grounded_actions_only_no_fabricated_remote_sensing"
    assert brief["is_grounded"] is True


def test_daily_ai_brief_empty_inputs_are_explicitly_not_grounded():
    brief = build_daily_ai_brief(field_id="f3", signals={}, tasks=[])
    assert brief["actions"][0]["action_id"] == "no-critical-action"
    assert brief["is_grounded"] is False
