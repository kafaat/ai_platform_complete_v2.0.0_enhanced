"""اختبار إغلاق ETc-dual الكنسيّ خلف feature flag (default off) — مستوى الإسقاط.

يقفل دالّة `_apply_canonical_etc_dual` (التي يستدعيها recompute_field_state على كتلة
`water`): العلم OFF ⇒ single_kc بلا تغيير (سلوك محفوظ)؛ ON + مدخلات ⇒ dual_kc بنفس ET0
الكنسيّ (et0_override) والملوحة غير مطبّقة (H5) وde_mm معلَن كافتراض؛ ON + نقص ⇒ single_kc +
سبب التعطيل. لا قاعدة بيانات — اختبار الدالّة النقيّة بمدخلات صريحة.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

try:
    from api.field_state_projection import _apply_canonical_etc_dual
    from core.season_phenology import resolve_crop_id
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)

_FLAG = "FEATURE_CANONICAL_ETC_DUAL"

# حمولة طقس كاملة (tmin/tmax/rh/wind/srad) — كافية لبناء WeatherDay ولـKe.
_PAYLOAD = {
    "daily": {
        "temperature_2m_max": [34.0],
        "temperature_2m_min": [18.0],
        "relative_humidity_2m_mean": [30.0],
        "wind_speed_10m_max": [3.0],
        "shortwave_radiation_sum": [25.0],
    }
}


def _base_water() -> dict:
    """كتلة water مفردة (نظير canonical_water): single ETc الأساس."""
    return {
        "et0_mm": 7.5,
        "etc_mm": 6.0,
        "etc_demand_class": "medium",
        "kc": 0.8,
        "source": "field_state.canonical",
    }


def _crop_id():
    return resolve_crop_id("قمح")  # → "wheat" (بطاقة موجودة)


def test_flag_off_keeps_single(monkeypatch):
    """العلم OFF (افتراضيّ) ⇒ single_kc بلا تغيير لـetc_mm (سلوك محفوظ)."""
    monkeypatch.delenv(_FLAG, raising=False)
    w = _base_water()
    _apply_canonical_etc_dual(w, _crop_id(), 60, 7.5, _PAYLOAD, 15.5, 0.6)
    assert w["etc_source"] == "single_kc"
    assert w["etc_mm"] == 6.0  # لم يتغيّر
    assert "etc_dual_mm" not in w


def test_flag_on_full_inputs_uses_dual(monkeypatch):
    """العلم ON + مدخلات كاملة ⇒ dual_kc؛ etc=dual بنفس ET0 الكنسيّ؛ assumptions مُعلَنة."""
    monkeypatch.setenv(_FLAG, "1")
    w = _base_water()
    _apply_canonical_etc_dual(w, _crop_id(), 60, 7.5, _PAYLOAD, 15.5, 0.6)
    assert w["etc_source"] == "dual_kc"
    assert "etc_dual_mm" in w and "etc_single_mm" in w
    assert w["etc_mm"] == w["etc_dual_mm"]  # التبديل (نمط المستخدم)
    assert w["et0_mm"] == 7.5  # ET0 الكنسيّ لم يتغيّر (مصدر واحد)
    assert "kcb" in w and "ke" in w
    # الملوحة غير مطبّقة + de معلَن كافتراض (صدق)
    assert "salinity_disabled_by_default" in w["dual_assumptions"]
    assert "surface_depletion_untracked_assumed_zero" in w["dual_assumptions"]


def test_flag_on_no_weather_falls_back_single(monkeypatch):
    """العلم ON لكن طقس غائب ⇒ تراجع single_kc + سبب معلَن (لا تلفيق)."""
    monkeypatch.setenv(_FLAG, "1")
    w = _base_water()
    _apply_canonical_etc_dual(w, _crop_id(), 60, 7.5, None, 15.5, 0.6)
    assert w["etc_source"] == "single_kc"
    assert w["etc_disabled_reason"] == "dual_inputs_unavailable"
    assert w["etc_mm"] == 6.0


def test_flag_on_partial_weather_falls_back_single(monkeypatch):
    """العلم ON + طقس ناقص (لا wind/rh) ⇒ تراجع single (Ke غير موثوق)."""
    monkeypatch.setenv(_FLAG, "1")
    w = _base_water()
    partial = {"daily": {"temperature_2m_max": [34.0], "temperature_2m_min": [18.0]}}
    _apply_canonical_etc_dual(w, _crop_id(), 60, 7.5, partial, 15.5, 0.6)
    assert w["etc_source"] == "single_kc"
    assert w["etc_disabled_reason"] == "dual_inputs_unavailable"


def test_flag_on_no_crop_falls_back_single(monkeypatch):
    """العلم ON لكن لا أساس (crop_id None) ⇒ single_kc + سبب التعطيل."""
    monkeypatch.setenv(_FLAG, "1")
    w = _base_water()
    _apply_canonical_etc_dual(w, None, 60, 7.5, _PAYLOAD, 15.5, 0.6)
    assert w["etc_source"] == "single_kc"
    assert w["etc_disabled_reason"] == "dual_inputs_unavailable"


def test_flag_on_no_ndvi_still_dual_age_based(monkeypatch):
    """العلم ON + لا NDVI ⇒ dual يتدرّج إلى Kcb من العمر (لا فشل، assumption مُعلَن)."""
    monkeypatch.setenv(_FLAG, "1")
    w = _base_water()
    _apply_canonical_etc_dual(w, _crop_id(), 60, 7.5, _PAYLOAD, 15.5, None)
    assert w["etc_source"] == "dual_kc"
    assert "etc_dual_mm" in w
