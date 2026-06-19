"""اختبارات جسر Kc المُشتقّ ⇐ CropKcProfile (kc_to_fao56_bridge) — نقيّ.

يثبت أنّ Kc المُشتقّ من المحاكاة يُغذّي ملفّ FAO-56 المُستخدَم في حساب الريّ، مع حفظ
خصائص بطاقة المحصول غير-Kc، ومعالجة المراحل الناقصة بأمان (دمج) أو بصراحة (بناء كامل).
"""

from __future__ import annotations

import pytest
from core.engines.fao56 import CropKcProfile, kc_for_age
from core.kc_extraction_engine import FaoStageKc
from core.kc_to_fao56_bridge import apply_derived_kc, stage_kc_to_crop_profile

pytestmark = pytest.mark.unit


def _card() -> CropKcProfile:
    return CropKcProfile(
        crop_id="wheat",
        kc_initial=0.30,
        kc_mid=1.15,
        kc_end=0.40,
        stage_days=[20, 30, 40, 30],
        salt_tolerance_ece=6.0,
        salt_slope_pct=7.1,
    )


def _stage(kc_ini=0.45, kc_mid=1.05, kc_end=0.55) -> FaoStageKc:
    return FaoStageKc(
        kc_ini=kc_ini,
        kc_mid=kc_mid,
        kc_end=kc_end,
        kcb_ini=0.15,
        kcb_mid=1.0,
        kcb_end=0.3,
    )


def test_apply_derived_kc_overrides_values_keeps_card_props():
    out = apply_derived_kc(_card(), _stage())
    # قيم Kc صارت المُشتقّة.
    assert out.kc_initial == 0.45 and out.kc_mid == 1.05 and out.kc_end == 0.55
    # خصائص البطاقة محفوظة.
    assert out.crop_id == "wheat"
    assert out.stage_days == [20, 30, 40, 30]
    assert out.salt_tolerance_ece == 6.0 and out.salt_slope_pct == 7.1
    assert "مُشتقّ" in out.source


def test_apply_derived_kc_missing_stage_falls_back_to_card():
    out = apply_derived_kc(_card(), _stage(kc_mid=None))
    # المرحلة الناقصة تُبقي قيمة البطاقة (لا اختلاق).
    assert out.kc_mid == 1.15
    # المراحل المعروفة تُبدَّل.
    assert out.kc_initial == 0.45 and out.kc_end == 0.55


def test_apply_derived_kc_does_not_mutate_input_card():
    card = _card()
    apply_derived_kc(card, _stage())
    assert card.kc_initial == 0.30 and card.kc_mid == 1.15  # البطاقة الأصليّة سليمة


def test_stage_kc_to_crop_profile_builds_full():
    prof = stage_kc_to_crop_profile(
        _stage(),
        crop_id="maize",
        stage_days=[25, 35, 40, 30],
        salt_tolerance_ece=1.7,
        salt_slope_pct=12.0,
    )
    assert prof.crop_id == "maize"
    assert prof.kc_initial == 0.45 and prof.kc_mid == 1.05 and prof.kc_end == 0.55
    assert prof.total_season_days == 130


def test_stage_kc_to_crop_profile_raises_on_missing_stage():
    with pytest.raises(ValueError, match="ناقص"):
        stage_kc_to_crop_profile(
            _stage(kc_end=None),
            crop_id="maize",
            stage_days=[25, 35, 40, 30],
            salt_tolerance_ece=1.7,
            salt_slope_pct=12.0,
        )


def test_bridged_profile_usable_by_fao56_kc_for_age():
    # الناتج صالح فعليّاً لحساب الريّ: kc_for_age يقبله ويُرجِع Kc منطقيّاً.
    prof = apply_derived_kc(_card(), _stage())
    kc, _stage_enum = kc_for_age(prof, 60)  # داخل مرحلة المنتصف
    assert 0.0 < float(kc) <= 1.5
    assert kc == prof.kc_mid  # يوم 60 ضمن المنتصف ⇒ Kc المُشتقّ للمنتصف
