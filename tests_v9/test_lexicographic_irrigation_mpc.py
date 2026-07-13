"""اختبار المتحكّم التنبّؤيّ الهرميّ المعجميّ للريّ (Lexicographic MPC, المرحلة 0) — نقيّ حتميّ.

يثبت: (أ) حقل جافّ في مرحلة حرجة ⇒ ريّ + حالة حماية المحصول + رموز أسباب صحيحة؛
(ب) الأولويّة المعجميّة: حماية المحصول (J1) غير قابلة للمقايضة مقابل توفير الماء (J2)؛
(ج) J2 يكسر التعادل نحو أقلّ ماءً حين تتساوى الحماية؛ (د) فشل-مُغلَق عند غياب الأفق أو
TAW غير صالح؛ (هـ) مطر كافٍ ⇒ تأجيل (hold) بلا اختلاق ريّ؛ (و) الطاقة/الآبار مُعلَنة
not_modelled دائماً؛ (ز) توصية-فقط: approval_required=True دائماً؛ (ح) التدهور يخفض الثقة.
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


def _dry(n=7, et0=10.0, kc=1.0, rain=0.0):
    return [ForecastDay(et0_mm=et0, kc=kc, rain_mm=rain) for _ in range(n)]


def test_dry_critical_stage_irrigates_under_crop_protection():
    # TAW=100, p=0.5 ⇒ RAW=50. Dr0=45، ETc=10 ⇒ عبور RAW يوم 0 في مرحلة الإزهار الحرجة.
    d = solve_lexicographic_irrigation(
        forecast=_dry(),
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=45.0,
        field_id="fld_a",
        growth_stage="flowering",
    )
    assert d.decision == "irrigate"
    assert d.target_depth_mm > 0
    assert d.operating_state is OperatingState.CROP_PROTECTION
    assert ReasonCode.CRITICAL_GROWTH_STAGE in d.reason_codes
    assert ReasonCode.ROOT_ZONE_APPROACHING_RAW in d.reason_codes
    # الريّ يُبقي منطقة الجذور خارج الإجهاد الحرج (J1 يقود).
    assert d.expected_root_zone_depletion_after_mm <= d.raw_mm
    assert d.stress_risk_after in ("normal", "watch")


def test_lexicographic_crop_protection_not_traded_for_water():
    # سلّم معجميّ: J1 (حماية) يُثبَّت أوّلاً؛ الخطّة الفائزة يجب ألّا تحوي أيّام إجهاد
    # في المرحلة الحرجة حين يمكن تفاديها — حتّى لو كانت خطّة أخرى أقلّ ماءً لكنّها تُجهِد.
    d = solve_lexicographic_irrigation(
        forecast=_dry(et0=12.0),
        taw_mm=80.0,
        raw_fraction=0.5,
        initial_depletion_mm=30.0,
        growth_stage="flowering",
    )
    assert d.objectives is not None
    # J1 للخطّة الفائزة = 0 (لا تجاوز RAW) — الحماية محقّقة قبل أيّ توفير.
    assert d.objectives.j1_crop_protection == pytest.approx(0.0, abs=1e-6)
    assert d.yield_floor_preserved is True


def test_water_tie_break_prefers_lower_consumption():
    # في مرحلة غير حرجة مع خطط متعدّدة تحقّق J1=0، يفوز الأقلّ ماءً (J2).
    d = solve_lexicographic_irrigation(
        forecast=_dry(et0=8.0),
        taw_mm=120.0,
        raw_fraction=0.5,
        initial_depletion_mm=20.0,
        growth_stage="vegetative",
    )
    # السياسة الفائزة يجب أن تكون من الطيف الموفِّر (sustainability/water_saving) لا yield_max
    # حين تتساوى الحماية — لأنّ J2 يكسر التعادل نحو أقلّ استهلاك.
    assert d.selected_policy in ("sustainability", "water_saving", "profit_max")
    assert d.objectives is not None
    assert d.objectives.j1_crop_protection == pytest.approx(0.0, abs=1e-6)


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
        growth_stage="vegetative",
    )
    assert d.decision == "hold"
    assert d.target_depth_mm == 0.0


def test_energy_and_wells_always_declared_not_modelled():
    d = solve_lexicographic_irrigation(
        forecast=_dry(), taw_mm=100.0, raw_fraction=0.5, initial_depletion_mm=10.0
    )
    assert "predicted_energy_kwh" in d.not_modelled
    assert "source_well_id" in d.not_modelled
    assert d.objectives is not None and d.objectives.energy_modelled is False
    # لا حالة ENERGY_CONSTRAINED في المرحلة 0 (لا بيانات طاقة).
    assert d.operating_state is not OperatingState.ENERGY_CONSTRAINED


def test_recommendation_only_and_uncalibrated():
    d = solve_lexicographic_irrigation(
        forecast=_dry(),
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=40.0,
        growth_stage="flowering",
    )
    assert d.approval_required is True
    assert d.calibrated is False
    assert d.yield_floor_basis == "stress_proxy_pending_ky"


def test_data_degraded_lowers_confidence():
    d = solve_lexicographic_irrigation(
        forecast=_dry(),
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=10.0,
        growth_stage="vegetative",
        data_degraded=True,
    )
    assert d.operating_state is OperatingState.DATA_DEGRADED
    assert d.confidence <= 0.4
    assert ReasonCode.DATA_DEGRADED in d.reason_codes


def test_budget_exhaustion_flags_water_scarcity():
    # ميزانيّة صغيرة جدّاً مع طلب عالٍ في مرحلة حرجة ⇒ إجهاد + شحّ ماء.
    d = solve_lexicographic_irrigation(
        forecast=_dry(et0=12.0, n=10),
        taw_mm=80.0,
        raw_fraction=0.5,
        initial_depletion_mm=35.0,
        growth_stage="flowering",
        season_budget_mm=15.0,
    )
    assert ReasonCode.WATER_BUDGET_LIMITED in d.reason_codes
    assert d.operating_state in (OperatingState.WATER_SCARCITY, OperatingState.CROP_PROTECTION)


def test_deterministic_repeatable():
    args = dict(
        forecast=_dry(),
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=40.0,
        growth_stage="flowering",
    )
    a = solve_lexicographic_irrigation(**args)
    b = solve_lexicographic_irrigation(**args)
    assert a.to_dict() == b.to_dict()
