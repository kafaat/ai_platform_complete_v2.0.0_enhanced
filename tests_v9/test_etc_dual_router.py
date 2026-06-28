"""اختبار وحدة للربط الاستهلاكيّ ETc المزدوج × NDVI — نقيّ بلا قاعدة.

يقفل: استخراج `crop_kc_profile` (DRY) + حفظ سلوك `stage_kc`، وجوهر تنسيق النقطة (بناء البروفايل من
البطاقة ثمّ `compute_etc_dual` بـNDVI حيّ مقابل عمريّ) — أي الفيزياء التي يحقنها الراوتر، دون DB.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from core.engines.fao56 import WeatherDay, compute_etc_dual  # noqa: E402
from core.season_phenology import (  # noqa: E402
    crop_kc_profile,
    resolve_crop_id,
    stage_kc,
)


def _weather() -> WeatherDay:
    return WeatherDay(34.0, 18.0, 45.0, 2.0, 24.0, 15.5, 1800.0, 180)


def test_crop_kc_profile_known_crop():
    """بطاقة معروفة (قمح) ⇒ CropKcProfile بقيم FAO-56 معقولة."""
    cid = resolve_crop_id("قمح")
    assert cid == "wheat"
    profile = crop_kc_profile(cid)
    assert profile is not None
    assert profile.crop_id == "wheat"
    assert 0.8 <= profile.kc_mid <= 1.4  # ذروة موسم معقولة
    assert len(profile.stage_days) == 4


def test_crop_kc_profile_unknown_is_none():
    """محصول مجهول/None ⇒ None (تدهور صادق، لا بروفايل مُلفَّق)."""
    assert crop_kc_profile("nonexistent_crop_xyz") is None
    assert crop_kc_profile(None) is None
    assert resolve_crop_id("نبات وهميّ") is None


def test_stage_kc_regression_after_extract():
    """حفظ السلوك: stage_kc بعد إعادة التهيئة ما زال يُرجِع Kc الطوريّ، None للمجهول."""
    cid = resolve_crop_id("قمح")
    assert stage_kc(cid, 60) is not None
    assert stage_kc(cid, None) is None
    assert stage_kc(None, 60) is None
    assert stage_kc("nonexistent_crop_xyz", 60) is None


def test_endpoint_core_wiring_ndvi_vs_age():
    """جوهر النقطة: NDVI الحيّ يشتقّ Kcb رصداً (يختلف عن العمريّ) ويُسجَّل في الافتراضات."""
    profile = crop_kc_profile(resolve_crop_id("قمح"))
    w, das = _weather(), 70
    age_based = compute_etc_dual(w, profile, das)  # ndvi=None ⇒ العمر
    low_ndvi = compute_etc_dual(w, profile, das, ndvi=0.35)  # غطاء جزئيّ ⇒ Kcb أدنى
    high_ndvi = compute_etc_dual(w, profile, das, ndvi=0.82)
    assert any("NDVI" in a for a in low_ndvi.assumptions)
    assert not any("NDVI" in a for a in age_based.assumptions)
    assert low_ndvi.kcb < age_based.kcb  # حقل مُجهَد/متأخّر ⇒ احتياج أدنى
    assert high_ndvi.kcb > low_ndvi.kcb
    # المخرَج يحمل ETc المزدوج (ما تردّه النقطة عبر asdict).
    assert low_ndvi.etc_dual_mm >= 0.0
