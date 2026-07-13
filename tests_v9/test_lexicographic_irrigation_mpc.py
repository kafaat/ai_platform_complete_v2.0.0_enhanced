"""اختبار المتحكّم التنبّؤيّ الهرميّ المعجميّ للريّ (Lexicographic MPC) — نقيّ حتميّ.

يغطّي المرحلتين:
- م0 (السلّم المعجميّ): حماية المحصول غير مقايَضة بالماء · فشل-مُغلَق · مطر⇒تأجيل ·
  الطاقة not_modelled · توصية-فقط · التدهور يخفض الثقة.
- م1 (نموذج Ky الكنسيّ J3): Ky حسب المحصول والمرحلة (FAO-33) · غياب Ky/المرحلة ⇒
  insufficient_data · ETm=0/غير منتهٍ ⇒ insufficient_data · J3 لا يتغلّب على J1 ·
  yield_floor_preserved لا يظهر بلا بيانات كاملة · حتميّة · أثر الأهداف + نَسَب المرشّح.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.irrigation_mpc import ForecastDay  # noqa: E402
from api.lexicographic_irrigation_mpc import (  # noqa: E402
    OperatingState,
    ReasonCode,
    solve_lexicographic_irrigation,
)
from core.engines.ky_registry import lookup_ky  # noqa: E402


def _dry(n=7, et0=10.0, kc=1.0, rain=0.0):
    return [ForecastDay(et0_mm=et0, kc=kc, rain_mm=rain) for _ in range(n)]


# ─────────────────────────── م0: السلّم المعجميّ ───────────────────────────


def test_dry_critical_stage_irrigates_under_crop_protection():
    d = solve_lexicographic_irrigation(
        forecast=_dry(),
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=45.0,
        field_id="fld_a",
        crop="maize",
        growth_stage="flowering",
    )
    assert d.decision == "irrigate"
    assert d.first_action_depth_mm > 0
    assert d.operating_state is OperatingState.CROP_PROTECTION
    assert ReasonCode.CRITICAL_GROWTH_STAGE in d.reason_codes
    assert d.expected_root_zone_depletion_after_mm <= d.raw_mm


def test_fail_closed_on_missing_forecast():
    d = solve_lexicographic_irrigation(
        forecast=[], taw_mm=100.0, raw_fraction=0.5, initial_depletion_mm=0.0, field_id="fld_b"
    )
    assert d.operating_state is OperatingState.EMERGENCY_FAIL_CLOSED
    assert d.decision == "hold"
    assert d.confidence == 0.0
    assert ReasonCode.MISSING_CRITICAL_INPUTS in d.reason_codes
    assert d.approval_required is True


def test_fail_closed_on_invalid_taw():
    d = solve_lexicographic_irrigation(
        forecast=_dry(), taw_mm=0.0, raw_fraction=0.5, initial_depletion_mm=0.0
    )
    assert d.operating_state is OperatingState.EMERGENCY_FAIL_CLOSED
    assert d.decision == "hold"


def test_rain_covers_need_holds_without_fabricating_irrigation():
    fc = [ForecastDay(et0_mm=3.0, kc=0.8, rain_mm=30.0) for _ in range(7)]
    d = solve_lexicographic_irrigation(
        forecast=fc,
        taw_mm=120.0,
        raw_fraction=0.5,
        initial_depletion_mm=5.0,
        crop="sorghum",
        growth_stage="vegetative",
    )
    assert d.decision == "hold"
    assert d.first_action_depth_mm == 0.0


def test_energy_and_wells_always_declared_not_modelled():
    d = solve_lexicographic_irrigation(
        forecast=_dry(), taw_mm=100.0, raw_fraction=0.5, initial_depletion_mm=10.0
    )
    assert "predicted_energy_kwh" in d.not_modeled
    assert "source_well_id" in d.not_modeled
    assert d.objectives is not None and d.objectives.energy_modelled is False
    assert d.operating_state is not OperatingState.ENERGY_CONSTRAINED


def test_recommendation_only_and_uncalibrated():
    d = solve_lexicographic_irrigation(
        forecast=_dry(),
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=40.0,
        crop="maize",
        growth_stage="flowering",
    )
    assert d.approval_required is True
    assert d.calibrated is False


def test_data_degraded_lowers_confidence():
    d = solve_lexicographic_irrigation(
        forecast=_dry(),
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=10.0,
        crop="sorghum",
        growth_stage="vegetative",
        data_degraded=True,
    )
    assert d.operating_state is OperatingState.DATA_DEGRADED
    assert d.confidence <= 0.4
    assert ReasonCode.DATA_DEGRADED in d.reason_codes


def test_budget_exhaustion_flags_water_scarcity():
    d = solve_lexicographic_irrigation(
        forecast=_dry(et0=12.0, n=10),
        taw_mm=80.0,
        raw_fraction=0.5,
        initial_depletion_mm=35.0,
        crop="maize",
        growth_stage="flowering",
        season_budget_mm=15.0,
    )
    assert ReasonCode.WATER_BUDGET_LIMITED in d.reason_codes
    assert d.operating_state in (OperatingState.WATER_SCARCITY, OperatingState.CROP_PROTECTION)


# ─────────────────────────── م1: نموذج Ky الكنسيّ ───────────────────────────


def test_ky_registry_crop_stage_values_are_sourced():
    # قيم FAO-33 حسب المحصول والمرحلة — لا اختلاق؛ كلّ مدخل يحمل مصدره.
    lk = lookup_ky("maize", "flowering")
    assert lk is not None
    assert lk.ky == pytest.approx(1.5)  # الذرة/التزهير — الأكثر حساسيّة
    assert lk.ky_basis == "crop_stage"
    assert "FAO-33" in lk.ky_source
    assert lk.version and lk.effective_from


def test_ky_per_stage_differs_within_crop():
    # Ky يختلف بالمرحلة داخل المحصول (لا قيمة موسميّة واحدة).
    veg = lookup_ky("maize", "vegetative").ky
    flow = lookup_ky("maize", "flowering").ky
    assert flow > veg


def test_ky_unknown_crop_falls_back_to_labeled_generic_stage():
    lk = lookup_ky("mango", "flowering")
    assert lk is not None
    assert lk.ky_basis == "generic_stage"  # مُعلَّم صراحةً — لا استبدال صامت
    assert lk.crop is None


def test_ky_unknown_stage_returns_none():
    assert lookup_ky("maize", "banana_time") is None
    assert lookup_ky("maize", None) is None


def test_j3_yield_response_computed_when_ky_available():
    # حقل مرويّ جيّداً في مرحلة الذرة الحرجة ⇒ ETa/ETm≈1 ⇒ غلّة نسبيّة عالية.
    d = solve_lexicographic_irrigation(
        forecast=_dry(et0=8.0),
        taw_mm=120.0,
        raw_fraction=0.5,
        initial_depletion_mm=20.0,
        crop="maize",
        growth_stage="flowering",
        yield_floor_ratio=0.85,
    )
    yr = d.yield_response
    assert yr.status == "ok"
    assert yr.ky == pytest.approx(1.5)
    assert yr.eta_over_etm is not None and yr.eta_over_etm >= 0.95
    assert yr.predicted_relative_yield is not None and yr.predicted_relative_yield >= 0.85
    assert d.yield_floor_preserved is True
    assert d.objective_trace["ky_source"] and d.candidate_lineage_id.startswith("mpc_")


def test_j3_insufficient_data_when_stage_missing():
    d = solve_lexicographic_irrigation(
        forecast=_dry(),
        taw_mm=120.0,
        raw_fraction=0.5,
        initial_depletion_mm=20.0,
        crop="maize",
        growth_stage=None,
    )
    assert d.yield_response.status == "insufficient_data"
    assert d.yield_floor_preserved is None  # لا تأكيد بلا بيانات
    assert ReasonCode.YIELD_DATA_INSUFFICIENT in d.reason_codes


def test_j3_insufficient_data_when_etm_zero():
    fc = [ForecastDay(et0_mm=0.0, kc=0.0, rain_mm=0.0) for _ in range(5)]
    d = solve_lexicographic_irrigation(
        forecast=fc,
        taw_mm=120.0,
        raw_fraction=0.5,
        initial_depletion_mm=10.0,
        crop="maize",
        growth_stage="flowering",
    )
    assert d.yield_response.status == "insufficient_data"
    assert d.yield_floor_preserved is None


def test_j3_out_of_bounds_on_severe_deficit_high_ky():
    # عجز شديد + Ky عالٍ (1.5) ⇒ الغلّة النسبيّة الخطّيّة سالبة ⇒ خارج الحدود، مقصوصة.
    fc = [ForecastDay(et0_mm=14.0, kc=1.1, rain_mm=0.0) for _ in range(7)]
    d = solve_lexicographic_irrigation(
        forecast=fc,
        taw_mm=60.0,
        raw_fraction=0.5,
        initial_depletion_mm=25.0,
        crop="maize",
        growth_stage="flowering",
        season_budget_mm=5.0,
        yield_floor_ratio=0.85,
    )
    assert d.yield_response.status == "out_of_bounds"
    assert d.yield_response.within_bounds is False
    assert 0.0 <= d.yield_response.predicted_relative_yield <= 1.0
    assert d.yield_floor_preserved is None  # خارج الحدود ⇒ لا تأكيد


def test_j3_does_not_override_j1():
    # حماية المحصول (J1) أعلى: الخطّة الفائزة يجب ألّا تُجهِد في مرحلة حرجة حتى لو خطّة
    # أخرى أعلى غلّة متوقّعة لكنّها تكسر الحماية. J1 للفائز = 0 دائماً حين يمكن تفاديه.
    d = solve_lexicographic_irrigation(
        forecast=_dry(et0=12.0),
        taw_mm=80.0,
        raw_fraction=0.5,
        initial_depletion_mm=30.0,
        crop="maize",
        growth_stage="flowering",
        yield_floor_ratio=0.9,
    )
    assert d.objectives is not None
    assert d.objectives.j1_crop_protection == pytest.approx(0.0, abs=1e-6)
    # القرار حُسِم عند مستوى ≥1 (J1 صفّى أوّلاً)، والحماية لم تُكسَر.
    assert d.expected_root_zone_depletion_after_mm <= d.raw_mm


def test_yield_floor_not_preserved_without_target_ratio():
    # بيانات كاملة لكن بلا هدف حدّ إنتاج ⇒ لا يمكن التأكيد ⇒ None (ليس True).
    d = solve_lexicographic_irrigation(
        forecast=_dry(et0=8.0),
        taw_mm=120.0,
        raw_fraction=0.5,
        initial_depletion_mm=20.0,
        crop="maize",
        growth_stage="flowering",
    )
    assert d.yield_response.status == "ok"
    assert d.yield_floor_preserved is None


def test_generic_stage_basis_lowers_confidence_vs_crop_specific():
    common = dict(
        forecast=_dry(et0=8.0),
        taw_mm=120.0,
        raw_fraction=0.5,
        initial_depletion_mm=20.0,
        growth_stage="vegetative",
    )
    crop_specific = solve_lexicographic_irrigation(crop="maize", **common)
    generic = solve_lexicographic_irrigation(crop="mango", **common)
    assert generic.yield_response.ky_basis == "generic_stage"
    assert crop_specific.yield_response.ky_basis == "crop_stage"
    assert generic.confidence < crop_specific.confidence


def test_deterministic_repeatable():
    args = dict(
        forecast=_dry(),
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=40.0,
        field_id="fld_z",
        crop="maize",
        growth_stage="flowering",
        yield_floor_ratio=0.85,
    )
    a = solve_lexicographic_irrigation(**args)
    b = solve_lexicographic_irrigation(**args)
    assert a.to_dict() == b.to_dict()
    assert a.candidate_lineage_id == b.candidate_lineage_id


def test_no_economic_margin_derived_from_ky():
    # حارس دلاليّ: J3 (Ky) لا يغذّي أيّ هامش/إيراد — economic_margin_delta يبقى None.
    d = solve_lexicographic_irrigation(
        forecast=_dry(et0=8.0),
        taw_mm=120.0,
        raw_fraction=0.5,
        initial_depletion_mm=20.0,
        crop="maize",
        growth_stage="flowering",
        water_price_per_m3=0.1,
    )
    assert d.economic_margin_delta is None


# ─────────────── P1.1: نَسَب/idempotency/حوكمة/تحقّق-مدخلات ───────────────


def _b(**kw):
    args = dict(
        forecast=_dry(),
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=40.0,
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        crop="maize",
        growth_stage="flowering",
    )
    args.update(kw)
    return solve_lexicographic_irrigation(**args)


def test_lineage_varies_with_constraints_no_collision():
    # الخلل المُثبَت سابقاً: قرارات مختلفة تشترك نَسَباً واحداً. الآن يجب أن تختلف.
    a = _b()
    b = _b(season_budget_mm=5.0)
    c = _b(max_application_mm=2.0)
    d = _b(water_price_per_m3=0.2)
    ids = {
        a.candidate_lineage_id,
        b.candidate_lineage_id,
        c.candidate_lineage_id,
        d.candidate_lineage_id,
    }
    assert len(ids) == 4  # لا تصادم
    assert len({a.content_digest, b.content_digest, c.content_digest, d.content_digest}) == 4


def test_idempotency_key_is_stable_across_constraint_changes():
    # مفتاح الطلب المنطقيّ ثابت (نفس الحقل/الموسم/الأفق) رغم اختلاف القيود.
    a = _b()
    b = _b(season_budget_mm=5.0)
    assert a.idempotency_key == b.idempotency_key
    assert a.content_digest != b.content_digest  # المحتوى يختلف


def test_lineage_and_idempotency_isolate_tenant_and_season():
    base = _b()
    other_tenant = _b(tenant_id="t2")
    other_season = _b(season_id="s2")
    assert base.idempotency_key != other_tenant.idempotency_key
    assert base.idempotency_key != other_season.idempotency_key
    assert base.content_digest != other_tenant.content_digest


def test_content_digest_full_sha256_hex():
    d = _b()
    assert len(d.content_digest) == 64  # sha256 كامل لا [:16]
    assert d.candidate_lineage_id == "mpc_" + d.content_digest[:16]


def test_fail_closed_on_non_finite_taw():
    d = solve_lexicographic_irrigation(
        forecast=_dry(), taw_mm=float("nan"), raw_fraction=0.5, initial_depletion_mm=10.0
    )
    assert d.operating_state is OperatingState.EMERGENCY_FAIL_CLOSED


def test_fail_closed_on_depletion_out_of_range():
    over = solve_lexicographic_irrigation(
        forecast=_dry(), taw_mm=100.0, raw_fraction=0.5, initial_depletion_mm=150.0
    )
    neg = solve_lexicographic_irrigation(
        forecast=_dry(), taw_mm=100.0, raw_fraction=0.5, initial_depletion_mm=-1.0
    )
    assert over.operating_state is OperatingState.EMERGENCY_FAIL_CLOSED
    assert neg.operating_state is OperatingState.EMERGENCY_FAIL_CLOSED


def test_fail_closed_on_non_finite_forecast():
    fc = [ForecastDay(et0_mm=float("inf"), kc=1.0, rain_mm=0.0) for _ in range(5)]
    d = solve_lexicographic_irrigation(
        forecast=fc, taw_mm=100.0, raw_fraction=0.5, initial_depletion_mm=10.0
    )
    assert d.operating_state is OperatingState.EMERGENCY_FAIL_CLOSED


def test_out_of_range_yield_floor_ratio_is_ignored():
    # هدف خارج [0,1] يُهمَل (لا يُحسَب عليه) — لا يُثبِت حدّ إنتاج على قيمة غير صالحة.
    d = _b(yield_floor_ratio=1.5)
    assert d.yield_floor_ratio is None
    assert d.yield_floor_preserved is None


def test_generic_stage_never_certifies_yield_floor():
    # Ky عامّ (محصول غير مسجَّل) لا يُثبِت حدّ الإنتاج مهما كان الهدف.
    d = solve_lexicographic_irrigation(
        forecast=_dry(et0=8.0),
        taw_mm=120.0,
        raw_fraction=0.5,
        initial_depletion_mm=20.0,
        crop="mango",
        growth_stage="flowering",
        yield_floor_ratio=0.5,
    )
    assert d.yield_response.ky_basis == "generic_stage"
    assert d.yield_floor_preserved is None


def test_execution_never_allowed_and_solver_versioned():
    d = _b()
    assert d.execution_allowed is False  # توصية-فقط
    assert d.solver_version and d.approval_required is True


def test_first_action_vs_horizon_total_separated():
    d = _b()
    # عمق اليوم الأوّل ≠ إجماليّ الأفق (J2 يقيّم الأفق كلّه).
    assert d.horizon_total_irrigation_mm >= d.first_action_depth_mm
    assert d.recommended_gross_water_m3_per_ha == d.first_action_depth_mm * 10.0
