from datetime import date

from core.lab_sampling import (
    GeoSamplePoint,
    SoilLabResult,
    analyze_soil_lab_result,
    classify_soil_ec,
    classify_soil_ph,
    lab_decision_context,
)


def test_geo_sample_point_validates_coordinates_and_soil_depth():
    ok = GeoSamplePoint(
        sample_id="s1",
        field_id="f1",
        kind="soil",
        latitude=15.1,
        longitude=44.2,
        depth_cm_from=0,
        depth_cm_to=30,
        sampled_on=date(2026, 6, 25),
        gps_accuracy_m=3.0,
    )
    assert ok.validate() == []
    bad = GeoSamplePoint(sample_id="", field_id="", kind="soil", latitude=99, longitude=200)
    assert set(bad.validate()) >= {
        "sample_id is required",
        "field_id is required",
        "latitude out of range",
        "longitude out of range",
        "soil sample depth range is required",
    }


def test_soil_lab_classification_flags_without_fabrication():
    out = analyze_soil_lab_result(
        SoilLabResult(sample_id="s1", ph=8.8, ec_dsm=6.2, organic_matter_pct=0.7, approved=True)
    )
    assert "pH خارج النطاق الملائم" in out["hazard_flags_ar"]
    assert "ملوحة تربة مرتفعة" in out["hazard_flags_ar"]
    assert "مادة عضوية منخفضة" in out["hazard_flags_ar"]
    assert set(out["missing_inputs"]) >= {"nitrogen_mg_kg", "phosphorus_mg_kg", "potassium_mg_kg"}
    assert out["decision_usable"] is False


def test_soil_lab_ready_only_when_approved_and_complete():
    result = SoilLabResult(
        sample_id="s2",
        ph=7.4,
        ec_dsm=1.2,
        organic_matter_pct=2.5,
        nitrogen_mg_kg=30,
        phosphorus_mg_kg=18,
        potassium_mg_kg=220,
        approved=True,
    )
    out = analyze_soil_lab_result(result)
    assert out["decision_usable"] is True
    ctx = lab_decision_context(soil=out, water=None)
    assert ctx["soil_lab_ready_for_fertilizer"] is True
    assert ctx["recommendation_gate"] == "allow"


def test_unapproved_soil_blocks_decision_gate():
    result = SoilLabResult(
        sample_id="s3",
        ph=7.4,
        ec_dsm=1.2,
        organic_matter_pct=2.5,
        nitrogen_mg_kg=30,
        phosphorus_mg_kg=18,
        potassium_mg_kg=220,
        approved=False,
    )
    out = analyze_soil_lab_result(result)
    ctx = lab_decision_context(soil=out, water=None)
    assert "نتيجة التربة غير معتمدة" in ctx["blockers_ar"]
    assert ctx["recommendation_gate"] == "needs_review"


def test_soil_threshold_edges():
    assert classify_soil_ph(7.8)["class"] == "acceptable"
    assert classify_soil_ph(8.6)["class"] == "strong_alkaline"
    assert classify_soil_ec(4.0)["class"] == "high"
    assert classify_soil_ec(8.0)["class"] == "severe"
