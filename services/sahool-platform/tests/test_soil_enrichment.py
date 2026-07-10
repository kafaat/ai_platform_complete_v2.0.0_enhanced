"""نَسَب مصدر ماء التربة + خفض الثقة (WS-D.2b) — التمييز بين lab/fallback صريح."""

from __future__ import annotations

from api.soil_enrichment import extract_texture, soil_water_provenance


def test_lab_texture_is_measured_no_penalty():
    out = soil_water_provenance(
        texture_known=True,
        texture_value="sandy_loam",
        texture_sampled_on="2026-05-01",
        texture_age_days=40.0,
        root_depth_supplied=True,
    )
    assert out["texture"]["source"] == "lab_measured"
    assert out["texture"]["value"] == "sandy_loam"
    assert out["texture"]["age_days"] == 40.0
    assert out["taw"]["source"] == "modelled_from_lab_texture"
    assert out["confidence_penalty"] == 0.0
    assert out["limitations"] == []


def test_missing_texture_is_fallback_with_penalty():
    out = soil_water_provenance(
        texture_known=False,
        texture_value=None,
        texture_sampled_on=None,
        texture_age_days=None,
        root_depth_supplied=True,
    )
    assert out["texture"]["source"] == "unavailable_fallback"
    assert out["taw"]["source"] == "modelled_generic_fallback"
    assert out["confidence_penalty"] == 0.15
    assert any("not lab-measured" in lim for lim in out["limitations"])


def test_default_root_depth_adds_penalty():
    out = soil_water_provenance(
        texture_known=True,
        texture_value="clay",
        texture_sampled_on="2026-05-01",
        texture_age_days=10.0,
        root_depth_supplied=False,
    )
    assert out["root_depth"]["source"] == "default_assumed"
    assert out["confidence_penalty"] == 0.10
    assert any("root depth" in lim for lim in out["limitations"])


def test_both_fallbacks_stack_penalty():
    out = soil_water_provenance(
        texture_known=False,
        texture_value=None,
        texture_sampled_on=None,
        texture_age_days=None,
        root_depth_supplied=False,
    )
    assert out["confidence_penalty"] == 0.25
    assert len(out["limitations"]) == 2
    assert out["taw"]["calibrated"] is False


def test_extract_texture_from_jsonb_variants():
    assert extract_texture({"texture": "loam"}) == "loam"
    assert extract_texture({"soil_texture": "clay"}) == "clay"
    assert extract_texture('{"texture": "silt"}') == "silt"  # JSON string
    assert extract_texture({"ph": 7.2}) is None  # لا نسيج
    assert extract_texture(None) is None
    assert extract_texture("not json") is None
