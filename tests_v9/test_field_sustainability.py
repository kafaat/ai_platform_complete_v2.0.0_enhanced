"""اختبار مؤشّر استدامة الحقل (Field Sustainability Index) — تجميع نقيّ.

يقفل: تجميع تربة+مياه من الإشارات الكنسيّة (يُعاد استخدام salinity_class/water_stress_class،
لا حساب)؛ **المغذّيات needs_data دائماً** (NPK غير مقيس — لا اختلاق)؛ إعادة تسوية الأوزان؛
بلا كربون؛ fail-safe. الأوزان/العتبات مُعلَنة (calibrated=False).
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
    from api.field_sustainability import compute_field_sustainability
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)


def test_healthy_field_high_with_nutrients_declared():
    """تربة سليمة + مياه سليمة ⇒ درجة عالية؛ المغذّيات needs_data (لا تُختلَق)."""
    s = compute_field_sustainability(
        {
            "salinity_class": "low",
            "ph": 7.0,
            "organic_matter": 2.5,
            "soil_age_days": 30,
            "water_stress_class": "normal",
        }
    )
    assert s["overall_score"] == 100.0
    assert s["level"] == "excellent"
    assert s["calibrated"] is False
    assert s["carbon"] == "excluded"  # بلا كربون صراحةً
    # المغذّيات معلَنة needs_data دائماً (NPK غير مقيس)
    assert s["dimensions"]["nutrients"]["score"] is None
    assert s["dimensions"]["nutrients"]["status"] == "needs_data"
    # يُعيد استخدام الصنف لا يحسبه
    assert s["dimensions"]["soil"]["salinity_class"] == "low"
    assert s["dimensions"]["water"]["water_stress_class"] == "normal"


def test_degraded_field_is_low():
    """ملوحة حرجة + كلسيّة + مادة عضويّة ضعيفة + تحليل قديم + إجهاد حرج ⇒ درجة منخفضة."""
    s = compute_field_sustainability(
        {
            "salinity_class": "critical",
            "ph": 8.2,
            "organic_matter": 0.5,
            "soil_age_days": 400,
            "water_stress_class": "critical",
        }
    )
    assert s["overall_score"] <= 30
    assert s["level"] in ("poor", "insufficient")


def test_weights_renormalized_when_soil_absent():
    """غياب التربة ⇒ يُحسب من المياه فقط (إعادة تسوية، لا عقاب على ما لا يُقاس)."""
    s = compute_field_sustainability({"water_stress_class": "normal"})
    assert s["dimensions"]["soil"]["score"] is None
    assert s["dimensions"]["water"]["score"] == 1.0
    assert s["overall_score"] == 100.0  # المياه وحدها بعد إعادة التسوية


def test_wue_included_in_water_dimension():
    """تمرير water_use_efficiency يُدمَج في بُعد المياه (متوسّط مع الإجهاد)."""
    s = compute_field_sustainability({"water_stress_class": "normal", "water_use_efficiency": 0.6})
    assert s["dimensions"]["water"]["score"] == 0.8  # mean(1.0, 0.6)


def test_no_signals_is_insufficient():
    """لا أيّ إشارة ⇒ insufficient (لا تلفيق استدامة)."""
    s = compute_field_sustainability({})
    assert s["overall_score"] == 0.0
    assert s["level"] == "insufficient"
    assert s["dimensions"]["nutrients"]["status"] == "needs_data"


def test_fail_safe_on_invalid_input():
    """مدخل غير قاموس ⇒ كتلة insufficient (لا رمي، صدق)."""
    for bad in (None, "nope", 42):
        s = compute_field_sustainability(bad)
        assert s["level"] == "insufficient"
        assert s["calibrated"] is False
