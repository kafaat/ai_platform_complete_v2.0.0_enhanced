"""اختبار وحدة لـKcb الديناميكيّ من NDVI (FAO-56 §9.4، Eq. 76-77) — نقيّ بلا قاعدة.

يقفل: كسر الغطاء من NDVI (مقصوص + معايرة)، معامل الكثافة Kd، Kcb=Kcb_full·Kd، وتكامله في
``compute_etc_dual`` مع **حفظ السلوك** عند غياب NDVI (لا انحدار للمسار القائم).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from core.engines.fao56 import (  # noqa: E402
    CropKcProfile,
    WeatherDay,
    compute_etc_dual,
    density_coefficient_kd,
    fractional_cover_from_ndvi,
    kcb_from_ndvi,
)


def _crop() -> CropKcProfile:
    # (crop_id, kc_initial, kc_mid, kc_end, stage_days, salt_tolerance_ece, salt_slope_pct)
    return CropKcProfile("test", 0.30, 1.15, 0.60, [20, 30, 40, 30], 6.8, 16.0)


def _weather() -> WeatherDay:
    # (temp_max_c, temp_min_c, humidity_pct, wind_speed_m_s, solar_radiation_mj_m2,
    #  latitude_deg, elevation_m, day_of_year)
    return WeatherDay(34.0, 18.0, 45.0, 2.0, 24.0, 15.5, 1800.0, 180)


def test_fc_from_ndvi_bounds_and_linearity():
    """fc مقصوص [0,1]: تربة عارية ⇒ 0، غطاء كامل ⇒ 1، والوسط خطّيّ."""
    assert fractional_cover_from_ndvi(0.15) == pytest.approx(0.0)
    assert fractional_cover_from_ndvi(0.85) == pytest.approx(1.0)
    assert fractional_cover_from_ndvi(0.50) == pytest.approx((0.50 - 0.15) / (0.85 - 0.15))
    # خارج المدى ⇒ مقصوص.
    assert fractional_cover_from_ndvi(0.05) == 0.0
    assert fractional_cover_from_ndvi(0.95) == 1.0


def test_fc_from_ndvi_invalid_bounds_raise():
    with pytest.raises(ValueError):
        fractional_cover_from_ndvi(0.5, ndvi_bare=0.8, ndvi_full=0.8)


def test_kd_monotonic_and_bounded():
    """Kd يزيد مع fc ومقصوص [0,1]: fc=0 ⇒ 0، fc=1 ⇒ 1."""
    assert density_coefficient_kd(0.0, 0.5) == 0.0
    assert density_coefficient_kd(1.0, 0.5) == pytest.approx(1.0)
    lo = density_coefficient_kd(0.3, 0.5)
    hi = density_coefficient_kd(0.6, 0.5)
    assert 0.0 < lo < hi <= 1.0


def test_kcb_from_ndvi_scales_full():
    """Kcb=Kcb_full·Kd: NDVI كامل ⇒ Kcb≈Kcb_full؛ تربة عارية ⇒ Kcb≈0."""
    kcb_hi, fc_hi = kcb_from_ndvi(0.85, kcb_full=1.10, crop_height_m=0.5)
    assert fc_hi == pytest.approx(1.0)
    assert kcb_hi == pytest.approx(1.10, rel=1e-6)
    kcb_lo, fc_lo = kcb_from_ndvi(0.15, kcb_full=1.10, crop_height_m=0.5)
    assert fc_lo == 0.0 and kcb_lo == 0.0


def test_compute_etc_dual_without_ndvi_unchanged():
    """حفظ السلوك: غياب NDVI ⇒ Kcb من العمر (لا انحدار)، والافتراضات تذكر الإزاحة لا NDVI."""
    r = compute_etc_dual(_weather(), _crop(), days_after_planting=60, et0_override=6.0)
    assert any("بإزاحة" in a for a in r.assumptions)
    assert not any("NDVI" in a for a in r.assumptions)


def test_compute_etc_dual_with_ndvi_observed_kcb():
    """مع NDVI: Kcb وfc مرصودان؛ NDVI منخفض ⇒ Kcb أدنى من مسار العمر (حقل مُجهَد/متأخّر)."""
    crop, w = _crop(), _weather()
    base = compute_etc_dual(
        w, crop, days_after_planting=70, et0_override=6.0
    )  # منتصف الموسم تقريباً
    low_ndvi = compute_etc_dual(w, crop, days_after_planting=70, ndvi=0.35, et0_override=6.0)
    assert any("NDVI" in a for a in low_ndvi.assumptions)
    # NDVI=0.35 (غطاء جزئيّ) ⇒ Kcb أدنى من Kcb منتصف الموسم الكامل.
    assert low_ndvi.kcb < base.kcb
    # NDVI عالٍ (غطاء شبه كامل) ⇒ Kcb مرتفع قريب من الذروة.
    high_ndvi = compute_etc_dual(w, crop, days_after_planting=70, ndvi=0.82, et0_override=6.0)
    assert high_ndvi.kcb > low_ndvi.kcb
