"""WELL-BLEND-WATER-QUALITY-NOT-COMPUTED-01 — EC/SAR of the blend actually applied to a field.

The binding resolver returned ``mixing_ratio`` verbatim and nothing computed the quality of the
blend. These tests pin the agronomy:

- EC of a blend = volume-weighted mean of source ECs (accepted linear approximation).
- SAR of a blend is NOT linear in the ratios: it is computed from blended Na/Ca/Mg (meq/L), and a
  weighted mean of per-source SARs is a different, wrong number.
- Missing ions ⇒ SAR ``not_computable`` (never 0, never a weighted SAR).
- Invalid / undeclared / non-unit-sum ratios ⇒ the blend is not computable.
"""

from __future__ import annotations

import math

import pytest
from api.irrigation_source_binding import summarize_blend_water_quality
from core.irrigation_water_analysis import (
    BLEND_COMPUTED,
    BLEND_NOT_COMPUTABLE,
    BLEND_PARTIAL,
    compute_blend_water_quality,
    compute_sar,
)

pytestmark = pytest.mark.unit


def _src(source_id, ratio, ec, na=None, ca=None, mg=None):
    return {
        "source_id": source_id,
        "mixing_ratio": ratio,
        "ec_ds_m": ec,
        "sodium_meq_l": na,
        "calcium_meq_l": ca,
        "magnesium_meq_l": mg,
    }


# ─── EC: volume-weighted mean ────────────────────────────────────────────


def test_two_source_blend_ec_is_volume_weighted_mean():
    out = compute_blend_water_quality([_src("w1", 0.5, 1.0), _src("w2", 0.5, 3.0)])
    assert out["ec_ds_m"]["status"] == BLEND_COMPUTED
    assert out["ec_ds_m"]["value"] == 2.0
    assert out["ec_ds_m"]["method"] == "volume_weighted_linear_mixing_approximation"


def test_unequal_ratios_weight_ec_by_volume():
    out = compute_blend_water_quality([_src("w1", 0.25, 1.0), _src("w2", 0.75, 3.0)])
    assert out["ec_ds_m"]["value"] == 2.5


def test_single_source_with_undeclared_ratio_is_the_whole_blend():
    # v214 contract: NULL mixing_ratio on the sole active source = sole source.
    out = compute_blend_water_quality([_src("w1", None, 1.7)])
    assert out["fractions"] == [{"source_id": "w1", "fraction": 1.0}]
    assert out["ec_ds_m"]["value"] == 1.7


def test_zero_fraction_source_does_not_need_data():
    out = compute_blend_water_quality([_src("w1", 1.0, 1.2), _src("w2", 0.0, None)])
    assert out["ec_ds_m"]["status"] == BLEND_COMPUTED
    assert out["ec_ds_m"]["value"] == 1.2


def test_missing_source_ec_is_not_computable_not_zero():
    out = compute_blend_water_quality([_src("w1", 0.5, 1.0), _src("w2", 0.5, None)])
    assert out["ec_ds_m"]["status"] == BLEND_NOT_COMPUTABLE
    assert out["ec_ds_m"]["value"] is None
    assert out["ec_ds_m"]["reason"] == "source_ec_missing"
    assert out["ec_ds_m"]["source_ids"] == ["w2"]


# ─── SAR: from blended ions, not averaged ───────────────────────────────


def test_blend_sar_is_computed_from_blended_ions_not_averaged_sars():
    # Soft canal water (low Na, high Ca+Mg) blended 50/50 with a sodic well (high Na, low Ca+Mg).
    canal = _src("canal", 0.5, 0.6, na=1.0, ca=4.0, mg=2.0)
    well = _src("well", 0.5, 3.0, na=12.0, ca=0.5, mg=0.5)
    out = compute_blend_water_quality([canal, well])

    # Blended ions: Na = 6.5, Ca = 2.25, Mg = 1.25 ⇒ SAR = 6.5 / √(3.5/2) = 4.91
    assert out["ions_meq_l"] == {
        "sodium_meq_l": 6.5,
        "calcium_meq_l": 2.25,
        "magnesium_meq_l": 1.25,
    }
    expected = round(6.5 / math.sqrt((2.25 + 1.25) / 2), 2)
    assert out["sar"]["status"] == BLEND_COMPUTED
    assert out["sar"]["method"] == "sar_from_blended_ions"
    assert out["sar"]["value"] == expected == 4.91

    # The tempting shortcut — weighting each source's SAR — gives a different, wrong answer.
    sar_canal = compute_sar(1.0, 4.0, 2.0)  # 0.58
    sar_well = compute_sar(12.0, 0.5, 0.5)  # 12 / √0.5 = 16.97
    assert (sar_canal, sar_well) == (0.58, 16.97)
    averaged = 0.5 * sar_canal + 0.5 * sar_well  # ≈ 8.78
    assert math.isclose(averaged, 8.775)
    assert abs(out["sar"]["value"] - averaged) > 3.0  # 4.91 vs 8.78: not a rounding difference
    assert out["status"] == BLEND_COMPUTED


def test_missing_ions_make_sar_not_computable_while_ec_still_computes():
    out = compute_blend_water_quality(
        [_src("w1", 0.5, 1.0, na=2.0, ca=2.0, mg=2.0), _src("w2", 0.5, 3.0)]
    )
    assert out["sar"]["status"] == BLEND_NOT_COMPUTABLE
    assert out["sar"]["value"] is None  # never 0, never a weighted SAR
    assert out["sar"]["reason"] == "source_ions_missing"
    assert out["sar"]["source_ids"] == ["w2"]
    assert out["ions_meq_l"] is None
    assert out["ec_ds_m"]["value"] == 2.0
    assert out["status"] == BLEND_PARTIAL


def test_zero_calcium_plus_magnesium_is_not_computable():
    out = compute_blend_water_quality([_src("w1", None, 1.0, na=5.0, ca=0.0, mg=0.0)])
    assert out["sar"]["status"] == BLEND_NOT_COMPUTABLE
    assert out["sar"]["reason"] == "calcium_plus_magnesium_zero"


def test_negative_or_nan_ion_is_rejected():
    out = compute_blend_water_quality([_src("w1", None, 1.0, na=-1.0, ca=2.0, mg=2.0)])
    assert out["sar"]["reason"] == "source_ions_invalid"
    out = compute_blend_water_quality([_src("w1", None, 1.0, na=float("nan"), ca=2.0, mg=2.0)])
    assert out["sar"]["reason"] == "source_ions_invalid"


# ─── ratio validation ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ratios, reason",
    [
        ((0.5, None), "mixing_ratio_undeclared"),
        ((None, None), "mixing_ratio_undeclared"),
        ((-0.2, 1.2), "mixing_ratio_invalid"),
        ((float("nan"), 0.5), "mixing_ratio_invalid"),
        ((float("inf"), 0.5), "mixing_ratio_invalid"),
        ((0.6, 0.6), "mixing_ratios_do_not_sum_to_one"),
        ((0.3, 0.3), "mixing_ratios_do_not_sum_to_one"),
    ],
)
def test_invalid_ratios_reject_the_whole_blend(ratios, reason):
    comps = [_src("w1", ratios[0], 1.0), _src("w2", ratios[1], 3.0)]
    out = compute_blend_water_quality(comps)
    assert out["status"] == BLEND_NOT_COMPUTABLE
    assert out["reason"] == reason
    assert out["ec_ds_m"]["value"] is None
    assert out["sar"]["value"] is None


def test_single_source_with_partial_ratio_is_not_the_whole_blend():
    # A lone source declared at 0.6 means 40 % of the blend is unaccounted for.
    out = compute_blend_water_quality([_src("w1", 0.6, 1.0)])
    assert out["reason"] == "mixing_ratios_do_not_sum_to_one"


def test_ratios_within_tolerance_are_normalised():
    out = compute_blend_water_quality([_src("w1", 0.4995, 1.0), _src("w2", 0.5, 3.0)])
    assert out["status"] != BLEND_NOT_COMPUTABLE
    assert math.isclose(sum(f["fraction"] for f in out["fractions"]), 1.0, abs_tol=1e-5)


def test_no_sources_is_not_computable():
    assert compute_blend_water_quality([])["reason"] == "no_active_sources"


# ─── binding adapter (shape the resolver actually returns) ───────────────


def _binding(source_id, ratio, ec):
    return {
        "water_source_id": source_id,
        "priority": 1,
        "mixing_ratio": ratio,
        "maximum_allowed_ec_ds_m": 3.0,
        "water_quality": None
        if ec is None
        else {"ec_ds_m": ec, "sampled_at": "2026-10-01T00:00:00+00:00", "quality": "certified"},
        "non_decision_grade_sample_present": False,
    }


def test_resolved_bindings_yield_blend_ec_and_honest_sar_state():
    # Live samples carry EC only (no ion columns in irrigation_water_quality_samples).
    out = summarize_blend_water_quality([_binding("w1", 0.5, 1.0), _binding("w2", 0.5, 3.0)])
    assert out["ec_ds_m"]["value"] == 2.0
    assert out["sar"]["status"] == BLEND_NOT_COMPUTABLE
    assert out["sar"]["reason"] == "source_ions_missing"
    assert out["gate_effect"] == "advisory_worst_source_gate_unchanged"


def test_resolved_bindings_without_decision_grade_sample_are_not_computable():
    out = summarize_blend_water_quality([_binding("w1", 0.5, 1.0), _binding("w2", 0.5, None)])
    assert out["ec_ds_m"]["reason"] == "source_ec_missing"
    assert out["ec_ds_m"]["source_ids"] == ["w2"]
