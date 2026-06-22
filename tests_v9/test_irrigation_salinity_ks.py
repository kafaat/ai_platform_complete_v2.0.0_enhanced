"""اختبارات وحدة: تصحيح الملوحة المحافظ (Maas-Hoffman Ks) في توصية الريّ الحيّة (H5).

منطق صرف — لا قاعدة ولا خدمات. يثبت:
  • حقل مالح (ECe ≥ العتبة، تحمّل المحصول معلوم) ⇒ عمق ريّ مُخفَّض + salinity_ks < 1.
  • حقل غير مالح (ECe < العتبة) ⇒ السلوك مطابق تماماً، salinity_ks = 1.0.
  • ECe مفقود ⇒ السلوك مطابق تماماً (لا تصحيح).
  • تحمّل المحصول مجهول (None) ⇒ السلوك مطابق تماماً (محافظ، لا نخمّن عتبة).
  • Ks مُثبَّت في [0,1] حتى عند ملوحة مفرطة.
  • لا يُضاف عمق غسيل: العمق المالح لا يتجاوز أبداً العمق غير المالح.

نُعيد استخدام عتبة الملوحة المتوسّطة الموحّدة (core.thresholds) بدل رقم مُصلَّب.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# نفس نمط بقيّة اختبارات tests_v9: نُدرِج جذر خدمة sahool-platform على sys.path
# حتى تُحلّ استيرادات (api.*, core.*) داخل weather_advice.
_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.weather_advice import irrigation_advice  # noqa: E402
from core.thresholds import SALINITY_MODERATE_ECE  # noqa: E402

# قيم محصول مرجعيّة (قمح، FAO-56 T23): عتبة 6.0 dS/m، ميل 7.1٪ لكلّ dS/m.
_WHEAT_THRESHOLD = 6.0
_WHEAT_SLOPE = 7.1

# مدخلات طقس ثابتة بلا مطر — كي يظهر أثر الملوحة على العمق صافياً.
_BASE = dict(et0_mm=6.0, crop="wheat", stage="mid", rain_recent_mm=0.0, forecast_rain_mm=0.0)


def _baseline() -> dict:
    """توصية أساسيّة بلا أيّ مدخلات ملوحة — المسار القديم."""
    return irrigation_advice(**_BASE)


class TestSalineFieldReducesDepth:
    def test_saline_field_reduces_recommended_depth(self):
        base = _baseline()
        saline = irrigation_advice(
            **_BASE,
            soil_ece=10.0,  # > العتبة 6.0
            crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
            salt_slope_pct=_WHEAT_SLOPE,
        )
        # Ks متوقّع = 1 - 7.1*(10-6)/100 = 0.716
        assert saline["salinity_ks"] == pytest.approx(0.716, abs=1e-3)
        assert 0.0 < saline["salinity_ks"] < 1.0
        # الملوحة تخفض الامتصاص ⇒ احتياج صافٍ أقلّ.
        assert saline["recommended_mm"] < base["recommended_mm"]
        # العمق المخفَّض ≈ العمق الأساسيّ × Ks (لا مطر يُخصَم هنا).
        assert saline["recommended_mm"] == pytest.approx(
            base["recommended_mm"] * saline["salinity_ks"], abs=0.15
        )

    def test_correction_is_traceable_in_payload_and_rationale(self):
        saline = irrigation_advice(
            **_BASE,
            soil_ece=12.0,
            crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
            salt_slope_pct=_WHEAT_SLOPE,
        )
        # حقل صريح ومُتتبَّع (غير مخفيّ).
        assert "salinity_ks" in saline
        assert saline["salinity_ks"] < 1.0
        assert "ملوح" in saline["rationale_ar"]

    def test_no_leaching_depth_added(self):
        """التصحيح المحافظ يَخفِض فقط — لا يزيد العمق أبداً (لا غسيل مضاف)."""
        base = _baseline()
        for ece in (4.0, 6.0, 8.0, 15.0, 40.0):
            saline = irrigation_advice(
                **_BASE,
                soil_ece=ece,
                crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
                salt_slope_pct=_WHEAT_SLOPE,
            )
            assert saline["recommended_mm"] <= base["recommended_mm"] + 1e-9


class TestNonSalineUnchanged:
    def test_ece_below_threshold_is_unchanged(self):
        base = _baseline()
        below = irrigation_advice(
            **_BASE,
            soil_ece=SALINITY_MODERATE_ECE - 0.5,  # تحت العتبة
            crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
            salt_slope_pct=_WHEAT_SLOPE,
        )
        assert below["salinity_ks"] == 1.0
        assert below["recommended_mm"] == base["recommended_mm"]
        assert below["rationale_ar"] == base["rationale_ar"]

    def test_ece_above_moderate_but_below_crop_threshold_no_reduction(self):
        """ECe ≥ العتبة المتوسّطة لكنّه ≤ عتبة تحمّل المحصول ⇒ Ks=1 (لا فقد غلّة)."""
        base = _baseline()
        r = irrigation_advice(
            **_BASE,
            soil_ece=_WHEAT_THRESHOLD,  # = 6.0 ≥ 4.0 لكنّه = عتبة المحصول
            crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
            salt_slope_pct=_WHEAT_SLOPE,
        )
        assert r["salinity_ks"] == 1.0
        assert r["recommended_mm"] == base["recommended_mm"]


class TestMissingInputsUnchanged:
    def test_missing_ece_is_unchanged(self):
        base = _baseline()
        r = irrigation_advice(
            **_BASE,
            soil_ece=None,
            crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
        )
        assert r["salinity_ks"] == 1.0
        assert r["recommended_mm"] == base["recommended_mm"]
        assert r["rationale_ar"] == base["rationale_ar"]

    def test_unknown_crop_tolerance_is_unchanged(self):
        base = _baseline()
        r = irrigation_advice(
            **_BASE,
            soil_ece=12.0,  # مالح، لكنّ عتبة المحصول مجهولة
            crop_salt_tolerance_ece=None,
        )
        assert r["salinity_ks"] == 1.0
        assert r["recommended_mm"] == base["recommended_mm"]
        assert r["rationale_ar"] == base["rationale_ar"]

    def test_no_salinity_args_matches_legacy_path(self):
        """استدعاء بلا أيّ وسائط ملوحة ⇒ مطابق للمسار القديم + salinity_ks=1.0."""
        r = _baseline()
        assert r["salinity_ks"] == 1.0


class TestKsClamped:
    def test_extreme_salinity_clamps_ks_to_zero(self):
        """ملوحة مفرطة (فقد ≥ 100٪) ⇒ Ks مُثبَّت عند 0.0 (لا قيمة سالبة)."""
        r = irrigation_advice(
            **_BASE,
            soil_ece=50.0,
            crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
            salt_slope_pct=_WHEAT_SLOPE,
        )
        assert r["salinity_ks"] == 0.0
        assert r["recommended_mm"] == 0.0

    def test_ks_always_within_unit_interval(self):
        for ece in (4.0, 5.0, 7.0, 9.0, 11.0, 20.0, 100.0):
            r = irrigation_advice(
                **_BASE,
                soil_ece=ece,
                crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
                salt_slope_pct=_WHEAT_SLOPE,
            )
            assert 0.0 <= r["salinity_ks"] <= 1.0


def test_payload_includes_salinity_ks_key_always():
    """الحقل موجود دائماً (صريح) سواء طُبّق التصحيح أم لا."""
    assert "salinity_ks" in _baseline()
    saline = irrigation_advice(**_BASE, soil_ece=10.0, crop_salt_tolerance_ece=_WHEAT_THRESHOLD)
    assert "salinity_ks" in saline
