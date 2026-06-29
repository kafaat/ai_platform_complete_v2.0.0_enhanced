"""اختبارات قبول: سياسة توصية الريّ المشروطة بالملوحة (H5).

منطق صرف — لا قاعدة ولا خدمات. يثبت السياسات الأربع وأرقامها الثلاثة:
  • net_only             — لا فحص EC ⇒ صافٍ فقط، لا Ks ولا غسل.
  • salinity_adjusted    — EC موثوق ≥ العتبة لكن بيانات الغسل ناقصة ⇒ Ks، لا غسل.
  • salinity_with_leaching — EC + ECw + صرف + كفاءة ⇒ Ks + غسل مشروط.
  • blocked_for_review   — ملوحة حرجة وبيانات غسل ناقصة ⇒ مراجعة خبير.

يثبت أيضاً: الراية ``force_net_only`` تُجبر المسار الصافي؛ الفحص القديم يُهمَل.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.irrigation_recommendation_policy import recommend_irrigation  # noqa: E402
from core.thresholds import SALINITY_CRITICAL_ECE  # noqa: E402

# طقس ثابت بلا مطر كي يظهر أثر الملوحة/الغسل على الأرقام صافياً.
_BASE = dict(et0_mm=6.0, crop="wheat", stage="mid", rain_recent_mm=0.0)
_WHEAT_THRESHOLD = 4.0  # عتبة منخفضة عمداً كي يتجاوزها ECe الاختباريّ
_SALINE = 6.0  # ≥ العتبة المتوسّطة، < الحرجة
_CRITICAL = SALINITY_CRITICAL_ECE + 2.0  # ملوحة حرجة


def test_net_only_when_no_ec():
    """لا فحص EC ⇒ net_only، لا Ks، لا غسل، لا حاجة لخبير."""
    r = recommend_irrigation(**_BASE, soil_ece=None)
    assert r["policy"] == "net_only"
    assert r["salinity_ks"] == 1.0
    assert r["salinity_leaching_mm"] == 0.0
    assert r["requires_expert_review"] is False
    assert r["net_irrigation_mm"] > 0


def test_salinity_adjusted_ks_no_leaching():
    """EC موثوق ≥ العتبة لكن بلا ECw/صرف/كفاءة ⇒ salinity_adjusted (Ks، لا غسل)."""
    r = recommend_irrigation(**_BASE, soil_ece=_SALINE, crop_salt_tolerance_ece=_WHEAT_THRESHOLD)
    assert r["policy"] == "salinity_adjusted"
    assert r["salinity_ks"] < 1.0  # ملوحة خفّضت الاحتياج
    assert r["salinity_leaching_mm"] == 0.0  # لا غسل بلا بياناته
    assert r["requires_expert_review"] is False
    # الاحتياج الصافي المالح ≤ غير المالح (الملوحة تخفض الامتصاص).
    base = recommend_irrigation(**_BASE, soil_ece=None)
    assert r["net_irrigation_mm"] <= base["net_irrigation_mm"]


def test_salinity_with_leaching_when_full_data():
    """EC + ECw + صرف مقبول + كفاءة ⇒ salinity_with_leaching (Ks + غسل)."""
    r = recommend_irrigation(
        **_BASE,
        soil_ece=_SALINE,
        crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
        water_ec=2.0,
        drainage="medium",
        irrigation_efficiency=0.85,
    )
    assert r["policy"] == "salinity_with_leaching"
    assert r["salinity_leaching_mm"] > 0.0  # غسل مُضاف
    # الإجماليّ يشمل الغسل والكفاءة ⇒ أكبر من الصافي.
    assert r["gross_irrigation_mm"] > r["net_irrigation_mm"]


def test_blocked_for_review_when_critical_without_leaching_data():
    """ملوحة حرجة وبيانات غسل ناقصة ⇒ blocked_for_review + يلزم خبير."""
    r = recommend_irrigation(**_BASE, soil_ece=_CRITICAL, crop_salt_tolerance_ece=_WHEAT_THRESHOLD)
    assert r["policy"] == "blocked_for_review"
    assert r["requires_expert_review"] is True
    assert r["salinity_leaching_mm"] == 0.0  # لا خطّة غسل مسؤولة


def test_force_net_only_disables_salinity():
    """الراية تُجبر المسار الصافي حتى مع EC مالح."""
    r = recommend_irrigation(
        **_BASE,
        soil_ece=_SALINE,
        crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
        force_net_only=True,
    )
    assert r["policy"] == "net_only"
    assert r["salinity_ks"] == 1.0


def test_stale_ec_treated_as_unreliable():
    """فحص EC أقدم من النافذة ⇒ يُهمَل (net_only)."""
    r = recommend_irrigation(
        **_BASE,
        soil_ece=_SALINE,
        soil_ec_age_days=900,
        crop_salt_tolerance_ece=_WHEAT_THRESHOLD,
        ec_max_age_days=365,
    )
    assert r["policy"] == "net_only"
    assert r["salinity_ks"] == 1.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
