"""اختبار وحدة لربط التفعيل التلقائيّ للملوحة بميزان الماء (H5) — مسارات بلا قاعدة/شبكة.

يقفل: `water_balance_auto` يفعّل الملوحة فقط عند تحليل موثوق (ECe قويّ + حديث + ثقة)، ويُطفئها بصدق
عند الغياب/القِدم — وأنّ مسار «لا تحليل» مطابق تماماً لـ`water_balance` المباشر (سلوك محفوظ).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

# استيراد طبقة الـAPI يتطلّب تبعيّات المنصّة؛ تُتخطّى الوحدة بصدق في بيئة CI «Unit Tests» الأدنى
# (بلا api/requirements) وتُغطّى في «Platform Unit Tests» — نمط test_etc_dual_weather.py.
try:
    from api.water_balance import WeatherInput, water_balance, water_balance_auto
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة
    pytest.skip("platform/api deps unavailable (minimal Unit Tests env)", allow_module_level=True)


def _weather() -> WeatherInput:
    return WeatherInput(
        t_min_c=18.0,
        t_max_c=34.0,
        solar_rad_mj_m2=24.0,
        rh_mean_pct=45.0,
        wind_2m_ms=2.0,
        latitude_deg=15.5,
        elevation_m=1800.0,
        day_of_year=180,
    )


def test_auto_enables_on_trusted_strong_soil():
    """ECe قويّ (3.0>2) + حديث (100ي) + ثقة 0.9 ⇒ تفعيل تلقائيّ + salinity_applied."""
    result, decision = water_balance_auto(
        _weather(),
        "قمح",
        "mid",
        soil_ece=3.0,
        analysis_age_days=100,
        confidence=0.9,
    )
    assert decision.enabled is True
    assert result.salinity_applied is True
    assert decision.reason_ar  # سبب مُعلَن


def test_auto_disabled_without_analysis_matches_plain():
    """بلا أيّ تحليل ⇒ off، والنتيجة مطابِقة لـwater_balance المباشر (سلوك محفوظ)."""
    w = _weather()
    result, decision = water_balance_auto(w, "قمح", "mid")
    assert decision.enabled is False
    assert result.salinity_applied is False
    plain = water_balance(w, "قمح", "mid")
    assert result.net_irrigation_mm == pytest.approx(plain.net_irrigation_mm)
    assert "salinity_applied" not in result.to_dict()  # شكل off مطابق للقائم


def test_auto_disabled_on_stale_analysis():
    """تحليل قديم (400ي≥365) ⇒ off (لا تفعيل على بيانات غير موثوقة)."""
    _result, decision = water_balance_auto(
        _weather(),
        "قمح",
        "mid",
        soil_ece=3.0,
        analysis_age_days=400,
        confidence=0.9,
    )
    assert decision.enabled is False


def test_auto_warns_saline_region_stale():
    """منطقة مالحة + تحليل قديم ⇒ off + تنبيه إعادة التحليل (warn)."""
    _result, decision = water_balance_auto(
        _weather(),
        "قمح",
        "mid",
        soil_ece=3.0,
        analysis_age_days=500,
        confidence=0.6,
        saline_region=True,
    )
    assert decision.enabled is False
    assert decision.warn is True
