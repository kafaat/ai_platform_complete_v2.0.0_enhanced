"""Farmland Phase 2 · 0002 — land quality kernels and their reclamation wiring."""

from datetime import date

import pytest
from land_quality import (
    SATURATION_EXTRACT_25C,
    LandQualityInputError,
    classify_salinity_sodicity,
    esp_from_exchangeable_na,
    esp_from_sar,
    gypsum_requirement,
    gypsum_requirement_from_exchangeable_na,
    land_capability,
)
from p3_products import LAB_HB60_VERSION_SUFFIX, build_reclamation_assessment

from shared.contracts.soil.p3 import ReclamationAssessmentRequest

pytestmark = pytest.mark.unit

ON = date(2026, 11, 25)


# ── ESP ─────────────────────────────────────────────────────────────────


def test_esp_from_exchangeable_na_is_the_hb60_ratio():
    r = esp_from_exchangeable_na(3.0, 20.0)
    assert r.esp_pct == 15.0 and r.basis == "measured_exchangeable_na"


@pytest.mark.parametrize(
    "na, cec, err",
    [
        (5.0, 0.0, "cec_cmolc_kg_out_of_range"),
        (-1.0, 20.0, "na_cmolc_kg_out_of_range"),
        (25.0, 20.0, "exchangeable_na_exceeds_cec"),
        (float("nan"), 20.0, "na_cmolc_kg_must_be_finite"),
        (1.0, float("inf"), "cec_cmolc_kg_must_be_finite"),
        (True, 20.0, "na_cmolc_kg_must_be_finite"),
    ],
)
def test_esp_from_exchangeable_na_rejects_impossible_inputs(na, cec, err):
    with pytest.raises(LandQualityInputError, match=err):
        esp_from_exchangeable_na(na, cec)


def test_esp_from_sar_matches_the_hb60_regression_and_is_labelled_an_estimate():
    # SAR 13 ⇒ ESR = -0.0126 + 0.19175 = 0.17915 ⇒ ESP = 17.915/1.17915 = 15.19 %
    r = esp_from_sar(13.0)
    assert r.esp_pct == pytest.approx(15.193, abs=1e-3)
    assert r.basis == "estimated_from_sar"


def test_esp_from_sar_floors_at_zero_where_the_regression_goes_negative():
    assert esp_from_sar(0.5).esp_pct == 0.0
    with pytest.raises(LandQualityInputError):
        esp_from_sar(-1.0)


# ── الجبس ───────────────────────────────────────────────────────────────


def test_gypsum_reproduces_the_classic_1_72_t_per_cmolc_in_15_cm():
    # 1 cmolc/kg Na replaced (CEC 10, ESP 20 → 10) in 15 cm at 1.33 t/m³ ≈ 1.72 t/ha
    r = gypsum_requirement(
        cec_cmolc_kg=10.0,
        esp_initial_pct=20.0,
        esp_target_pct=10.0,
        depth_m=0.15,
        bulk_density_t_m3=1.33,
    )
    assert r.na_to_replace_cmolc_kg == 1.0
    assert r.gypsum_t_per_ha == pytest.approx(1.717, abs=1e-3)
    assert r.assumptions["requirement_basis"] == "theoretical"


def test_gypsum_scales_with_purity_and_declared_efficiency_factor():
    base = dict(
        cec_cmolc_kg=20.0,
        esp_initial_pct=25.0,
        esp_target_pct=10.0,
        depth_m=0.3,
        bulk_density_t_m3=1.4,
    )
    theo = gypsum_requirement(**base).gypsum_t_per_ha
    adj = gypsum_requirement(**base, purity=0.8, exchange_efficiency_factor=1.25)
    assert theo == pytest.approx(10.847, abs=1e-3)
    assert adj.gypsum_t_per_ha == pytest.approx(theo * 1.25 / 0.8, rel=1e-4)
    assert adj.assumptions["requirement_basis"] == "efficiency_adjusted"


def test_gypsum_is_zero_when_target_is_not_below_current():
    r = gypsum_requirement(
        cec_cmolc_kg=20.0,
        esp_initial_pct=8.0,
        esp_target_pct=10.0,
        depth_m=0.3,
        bulk_density_t_m3=1.4,
    )
    assert r.gypsum_t_per_ha == 0.0 and r.na_to_replace_cmolc_kg == 0.0


@pytest.mark.parametrize(
    "override",
    [
        {"cec_cmolc_kg": 0.0},
        {"esp_initial_pct": 120.0},
        {"depth_m": 0.0},
        {"depth_m": 5.0},
        {"bulk_density_t_m3": 3.5},
        {"purity": 0.0},
        {"exchange_efficiency_factor": 0.8},
        {"cec_cmolc_kg": float("nan")},
    ],
)
def test_gypsum_rejects_out_of_range_inputs(override):
    base = dict(
        cec_cmolc_kg=20.0,
        esp_initial_pct=25.0,
        esp_target_pct=10.0,
        depth_m=0.3,
        bulk_density_t_m3=1.4,
    )
    with pytest.raises(LandQualityInputError):
        gypsum_requirement(**{**base, **override})


# ── HB60 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ece, esp, expected",
    [
        (1.0, 5.0, "normal"),
        (6.0, 5.0, "saline"),
        (1.0, 20.0, "sodic"),
        (6.0, 20.0, "saline_sodic"),
        (4.0, 15.0, "saline_sodic"),  # thresholds are inclusive of the bad class (≥)
    ],
)
def test_hb60_soil_class(ece, esp, expected):
    r = classify_salinity_sodicity(
        ece_ds_m=ece,
        ec_method=SATURATION_EXTRACT_25C,
        esp_pct=esp,
        observed_on=date(2026, 9, 1),
        source="lab",
        on=ON,
    )
    assert (r.soil_class, r.complete, r.freshness) == (expected, True, "enforced")


def test_hb60_class_is_withheld_when_a_measurement_is_missing_or_stale():
    missing = classify_salinity_sodicity(
        ece_ds_m=6.0,
        ec_method=SATURATION_EXTRACT_25C,
        esp_pct=None,
        observed_on=date(2026, 9, 1),
        source="lab",
        on=ON,
    )
    assert missing.soil_class is None and not missing.complete
    assert "sodic.ESP:missing_observation" in missing.reason
    # the determined half still stands on its own (F6: ECe >= 4 is saline whatever ESP is)
    assert (missing.saline, missing.sodic) == (True, None)
    stale = classify_salinity_sodicity(
        ece_ds_m=1.0,
        ec_method=SATURATION_EXTRACT_25C,
        esp_pct=5.0,
        observed_on=date(2020, 1, 1),
        source="lab",
        on=ON,
    )
    assert stale.soil_class is None and "observation_stale" in stale.reason


def test_hb60_without_a_sample_date_classifies_but_declares_freshness_unverifiable():
    r = classify_salinity_sodicity(
        ece_ds_m=6.0,
        ec_method=SATURATION_EXTRACT_25C,
        esp_pct=20.0,
        observed_on=None,
        source="lab",
        on=ON,
    )
    assert r.soil_class == "saline_sodic"
    assert r.freshness == "not_verifiable_no_sample_date"
    assert r.to_dict()["freshness"] == "not_verifiable_no_sample_date"


# ── صنف القدرة ─────────────────────────────────────────────────────────


def _lcc(**kw):
    base = dict(
        slope_pct=1.0, effective_depth_cm=120.0, ece_ds_m=1.0, esp_pct=3.0, drainage_class="well"
    )
    return land_capability(**{**base, **kw})


def test_land_capability_class_one_has_no_limiting_subclass():
    r = _lcc()
    assert (r.capability_class, r.limiting_subclasses, r.complete, r.arable) == (
        "I",
        [],
        True,
        True,
    )


def test_worst_factor_sets_the_class_and_names_every_subclass_at_that_class():
    r = _lcc(slope_pct=8.0, ece_ds_m=5.0)  # slope III (e) and ECe III (s)
    assert r.capability_class == "III"
    assert r.limiting_subclasses == ["e", "s"]
    r = _lcc(esp_pct=30.0)  # ESP ≥ 25 ⇒ VI — not arable
    assert (r.capability_class, r.limiting_subclasses, r.arable) == ("VI", ["s"], False)
    r = _lcc(drainage_class="very_poor")
    assert (r.capability_class, r.limiting_subclasses) == ("V", ["w"])


def test_shallow_soil_drops_the_class():
    assert _lcc(effective_depth_cm=60.0).capability_class == "III"
    assert _lcc(effective_depth_cm=10.0).capability_class == "VII"


def test_a_missing_factor_makes_the_class_provisional_not_final():
    r = _lcc(esp_pct=None)
    assert r.capability_class is None and not r.complete
    assert r.best_possible_class == "I"  # the true class can only be I or worse
    assert r.arable is None  # unknown until the sodicity factor is measured
    assert next(f for f in r.factors if f.factor == "esp_pct").status == "missing"


def test_a_known_non_arable_factor_settles_arability_even_when_incomplete():
    r = _lcc(slope_pct=35.0, drainage_class=None)
    assert r.capability_class is None and r.best_possible_class == "VII" and r.arable is False


@pytest.mark.parametrize(
    "kw", [{"slope_pct": -2.0}, {"effective_depth_cm": float("nan")}, {"drainage_class": "swampy"}]
)
def test_invalid_factor_values_are_flagged_and_keep_the_class_provisional(kw):
    r = _lcc(**kw)
    assert r.capability_class is None and not r.complete
    assert any(f.status == "invalid" for f in r.factors)


def test_land_capability_serialises_its_standard_and_calibration_status():
    out = _lcc().to_dict()
    assert out["standard"] == "USDA-AH210-INDICATIVE@v1" and out["calibrated_for_region"] is False


# ── الربط بتقييم الاستصلاح ─────────────────────────────────────────────


def _reclaim(**kw):
    base = dict(
        tenant_id="t1",
        field_id="f1",
        geometry_hash="g1",
        salinity_probability=0.1,
        sodicity_probability=0.1,
        gypsum_probability=0.1,
        stoniness_fraction=0.0,
        compaction_risk=0.1,
        leveling_need=0.1,
        drainage_need="none",
        crop_suitability_score=0.8,
    )
    return build_reclamation_assessment(ReclamationAssessmentRequest(**{**base, **kw}))


def test_lab_verified_sodic_soil_raises_gypsum_candidate_even_at_low_screening_probability():
    p = _reclaim(lab_verified=True, ec_lab_ds_m=2.0, esp_pct=22.0)
    gypsum = next(i for i in p.interventions if i["type"] == "gypsum_candidate")
    assert gypsum["basis"] == "lab_hb60"
    assert gypsum["rate_kernel"] == "land_quality.gypsum_requirement"
    assert gypsum["rate_inputs_missing"] == ["cec_cmolc_kg", "depth_m", "bulk_density_t_m3"]
    lab = p.provenance["lab_salinity_sodicity"]
    # sodicity half determined by ESP alone; salinity half withheld (P3 carries no EC method)
    assert (lab["sodic"], lab["saline"], lab["soil_class"]) == (True, None, None)
    assert lab["freshness"] == "not_verifiable_no_sample_date"
    assert "gypsum_candidate" in p.phased_plan[2]["actions"]


def test_p3_ec_of_unknown_method_never_yields_a_stored_normal_class():
    # Hospital F1: a 1:5 EC of 1.5 dS/m (~ECe 8-10, saline) used to be read as ECe and stored
    # as soil_class "normal" citing the saturated-paste method.
    p = _reclaim(lab_verified=True, ec_lab_ds_m=1.5, esp_pct=5.0)
    lab = p.provenance["lab_salinity_sodicity"]
    assert lab["soil_class"] is None and lab["saline"] is None and lab["sodic"] is False
    assert any(
        w.startswith("saline.ECe:ec_method_not_saturation_extract_25c") for w in lab["withheld"]
    )
    assert not any(i.get("basis") == "lab_hb60" for i in p.interventions)


def test_p3_high_ec_without_method_raises_no_lab_leaching_candidate():
    p = _reclaim(lab_verified=True, ec_lab_ds_m=9.0, esp_pct=4.0)
    assert not any(i.get("basis") == "lab_hb60" for i in p.interventions)
    assert p.provenance["lab_salinity_sodicity"]["saline"] is None


def test_unverified_lab_values_are_not_classified_and_change_nothing():
    p = _reclaim(lab_verified=False, ec_lab_ds_m=9.0, esp_pct=22.0)
    assert "lab_salinity_sodicity" not in p.provenance
    assert not any(i["type"] in {"gypsum_candidate", "leaching_candidate"} for i in p.interventions)
    assert p.assessment_version == "reclamation-v1"


def test_unverified_esp_is_not_echoed_on_a_screening_gypsum_candidate():
    p = _reclaim(lab_verified=False, sodicity_probability=0.6, esp_pct=22.0)
    gypsum = next(i for i in p.interventions if i["type"] == "gypsum_candidate")
    assert "esp_pct" not in gypsum and "rate_kernel" not in gypsum


def test_low_lab_esp_adds_no_amendment():
    p = _reclaim(lab_verified=True, ec_lab_ds_m=1.0, esp_pct=4.0)
    assert p.provenance["lab_salinity_sodicity"]["sodic"] is False
    assert not any(i["type"] in {"gypsum_candidate", "leaching_candidate"} for i in p.interventions)


def test_ec_only_lab_values_determine_no_half_in_p3():
    p = _reclaim(lab_verified=True, ec_lab_ds_m=9.0)
    lab = p.provenance["lab_salinity_sodicity"]
    assert lab["soil_class"] is None and lab["complete"] is False
    assert (lab["saline"], lab["sodic"]) == (None, None)
    assert not any(i.get("basis") == "lab_hb60" for i in p.interventions)


def test_lab_classified_products_are_stored_under_their_own_version_key():
    # Hospital nit 10: p3_store upserts on (..., version, identity_hash); new output semantics
    # must not silently overwrite a pre-Phase-2 payload stored under the same version.
    assert _reclaim(lab_verified=True, esp_pct=4.0).assessment_version == (
        f"reclamation-v1+{LAB_HB60_VERSION_SUFFIX}"
    )
    assert _reclaim(sodicity_probability=0.6).assessment_version == "reclamation-v1"


def test_ec_by_another_method_is_withheld_with_its_method_named():
    r = classify_salinity_sodicity(
        ece_ds_m=1.5,
        ec_method="soil_water_1_5",
        esp_pct=20.0,
        observed_on=date(2026, 9, 1),
        source="lab",
        on=ON,
    )
    assert (r.saline, r.sodic, r.soil_class) == (None, True, None)
    assert r.withheld == ("saline.ECe:ec_method_not_saturation_extract_25c:soil_water_1_5",)


def test_screening_probability_path_is_unchanged_when_no_lab_values_exist():
    p = _reclaim(sodicity_probability=0.6)
    gypsum = next(i for i in p.interventions if i["type"] == "gypsum_candidate")
    assert gypsum == {"type": "gypsum_candidate", "requires": "lab_EC_ESP_and_water_profile"}


def test_gypsum_from_measured_exchangeable_na_records_the_measured_basis():
    r = gypsum_requirement_from_exchangeable_na(
        cec_cmolc_kg=20.0,
        na_exchangeable_cmolc_kg=5.0,
        esp_target_pct=10.0,
        depth_m=0.3,
        bulk_density_t_m3=1.4,
    )
    # ESP 25 → 10 on CEC 20 = 3 cmolc/kg, identical to the ESP-based path
    assert r.na_to_replace_cmolc_kg == 3.0
    assert r.gypsum_t_per_ha == pytest.approx(10.847, abs=1e-3)
    assert r.assumptions["esp_basis"] == "measured_exchangeable_na"
    assert r.inputs["na_exchangeable_cmolc_kg"] == 5.0


def test_gypsum_from_exchangeable_na_refuses_na_above_cec():
    with pytest.raises(LandQualityInputError, match="exchangeable_na_exceeds_cec"):
        gypsum_requirement_from_exchangeable_na(
            cec_cmolc_kg=10.0,
            na_exchangeable_cmolc_kg=12.0,
            esp_target_pct=5.0,
            depth_m=0.3,
            bulk_density_t_m3=1.4,
        )


def test_every_land_capability_factor_names_its_source():
    for f in _lcc(esp_pct=None).to_dict()["factors"]:
        assert "AH-210" in f["source"] or "AH210" in f["source"], f
    slope = next(f for f in _lcc().to_dict()["factors"] if f["factor"] == "slope_pct")
    assert slope["source"].startswith("USDA-AH210-INDICATIVE@v1#slope")
