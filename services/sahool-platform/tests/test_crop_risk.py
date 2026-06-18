"""اختبارات وحدة لمحرّك المخاطر الزراعيّة (core/crop_risk) — نقيّ حتميّ."""

from __future__ import annotations

import pytest
from core.crop_risk import CropRisk, assess_crop_risk

pytestmark = pytest.mark.unit


def _by_type(risks: list[CropRisk]) -> dict[str, CropRisk]:
    return {r.risk_type: r for r in risks}


def test_fungal_sensitive_crop_high_disease_triggers_high():
    """البطاطس (حسّاسة للّفحة) عند خطر مرض عالٍ ⇒ خطر فطريّ بشدّة عالية."""
    risks = assess_crop_risk(
        "potato",
        disease_risk_score=0.95,
        heat_stress_hours=0,
        frost_risk_hours=0,
    )
    by = _by_type(risks)
    assert "fungal_disease" in by
    assert by["fungal_disease"].severity == "high"
    assert by["fungal_disease"].crop == "potato"
    assert "بطاطس" in by["fungal_disease"].reason_ar


def test_tolerant_disease_case_does_not_trigger():
    """درجة خطر مرض منخفضة تحت عتبة الحسّاسيّة ⇒ لا خطر فطريّ."""
    risks = assess_crop_risk(
        "potato",
        disease_risk_score=0.1,
        heat_stress_hours=0,
        frost_risk_hours=0,
    )
    assert all(r.risk_type != "fungal_disease" for r in risks)


def test_frost_sensitive_crop_triggers_frost_damage():
    """الطماطم (حسّاسة للصقيع) مع ساعات صقيع ⇒ خطر ضرر صقيع مُحفَّز."""
    risks = assess_crop_risk(
        "tomato",
        disease_risk_score=0.0,
        heat_stress_hours=0,
        frost_risk_hours=6,
    )
    by = _by_type(risks)
    assert "frost_damage" in by
    assert by["frost_damage"].score > 0.0


def test_heat_tolerant_date_palm_needs_more_hours():
    """النخيل (متحمّل للحرارة) لا يتحفّز بساعات تحفّز محصولاً حسّاساً كالطماطم."""
    hours = 6
    palm = assess_crop_risk(
        "date_palm",
        disease_risk_score=0.0,
        heat_stress_hours=hours,
        frost_risk_hours=0,
    )
    tomato = assess_crop_risk(
        "tomato",
        disease_risk_score=0.0,
        heat_stress_hours=hours,
        frost_risk_hours=0,
    )
    assert all(r.risk_type != "heat_stress" for r in palm)  # تحت عتبة النخيل
    assert any(r.risk_type == "heat_stress" for r in tomato)  # فوق عتبة الطماطم

    # وبساعات كافية يتحفّز النخيل أيضاً.
    palm_hot = assess_crop_risk(
        "date_palm",
        disease_risk_score=0.0,
        heat_stress_hours=24,
        frost_risk_hours=0,
    )
    assert any(r.risk_type == "heat_stress" for r in palm_hot)


def test_unknown_crop_uses_default_and_does_not_crash():
    """محصول غير معروف يستخدم الملفّ الافتراضيّ دون تعطُّل."""
    risks = assess_crop_risk(
        "alien_crop",
        disease_risk_score=0.99,
        heat_stress_hours=20,
        frost_risk_hours=20,
    )
    types = {r.risk_type for r in risks}
    assert types == {"fungal_disease", "heat_stress", "frost_damage"}
    for r in risks:
        assert r.crop == "alien_crop"


def test_scores_clamped_to_unit_interval():
    """مع مدخلات قصوى (وتجاوز [0,1]) تبقى كلّ الدرجات ضمن [0,1]."""
    risks = assess_crop_risk(
        "wheat",
        disease_risk_score=5.0,  # خارج [0,1] عمداً
        heat_stress_hours=1000,
        frost_risk_hours=1000,
        humidity_avg_percent=100.0,
    )
    assert risks
    for r in risks:
        assert 0.0 <= r.score <= 1.0
        assert r.severity in {"low", "moderate", "high"}


def test_benign_weather_returns_empty_list():
    """طقس حميد (لا إشارات خطر) ⇒ قائمة مخاطر فارغة."""
    risks = assess_crop_risk(
        "wheat",
        disease_risk_score=0.0,
        heat_stress_hours=0,
        frost_risk_hours=0,
    )
    assert risks == []


def test_humidity_boost_raises_disease_score():
    """الرطوبة العالية تُعزّز درجة خطر المرض عند تحفُّزه."""
    base = assess_crop_risk(
        "tomato",
        disease_risk_score=0.4,
        heat_stress_hours=0,
        frost_risk_hours=0,
    )
    humid = assess_crop_risk(
        "tomato",
        disease_risk_score=0.4,
        heat_stress_hours=0,
        frost_risk_hours=0,
        humidity_avg_percent=92.0,
    )
    b = _by_type(base)["fungal_disease"]
    h = _by_type(humid)["fungal_disease"]
    assert h.score > b.score
