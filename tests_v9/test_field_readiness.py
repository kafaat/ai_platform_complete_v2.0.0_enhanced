"""اختبار مؤشّر جاهزيّة بيانات الحقل (Field Data Readiness Index) — تجميع نقيّ.

يقفل: تجميع الإشارات القائمة (نضارة/ثقة/معايرة/تغطية) في درجة + مستوى + إرشاد عمليّ؛
إعادة تسوية الأوزان على الأبعاد المتاحة (لا عقاب على ما لا يُقاس)؛ صدق المدخل الفاسد (None).
الأوزان مُعلَنة لا معايَرة (calibrated=False).
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
    from api.field_readiness import compute_field_readiness
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)


def _strong_state() -> dict:
    return {
        "confidence_level": "high",
        "inputs": {"ndvi_age_days": 2, "soil_age_days": 30, "weather_age_hours": 5},
        "remote_sensing": {"available": True, "calibration_status": "calibrated"},
        "agronomic": {},
        "water": {},
        "boundary": {},
    }


def test_strong_field_is_excellent():
    """كلّ الأبعاد قويّة ⇒ درجة عالية ومستوى excellent + مصدر مُعلَن."""
    r = compute_field_readiness(_strong_state())
    assert r is not None
    assert r["overall_score"] == 100.0
    assert r["level"] == "excellent"
    assert r["source"] == "field_state.canonical"
    assert r["calibrated"] is False  # الأوزان غير معايَرة (صدق)
    assert r["dimensions"]["coverage"]["signals_present"] == 4
    assert r["actionable_ar"] == []  # لا شيء يُحسَّن


def test_stale_partial_is_fair_with_actions():
    """NDVI قديم + لا تربة + ثقة منخفضة ⇒ مستوى أدنى + إرشاد عمليّ صادق."""
    state = {
        "confidence_level": "low",
        "inputs": {"ndvi_age_days": 18, "soil_age_days": None, "weather_age_hours": 10},
        "remote_sensing": {
            "available": True,
            "calibration_status": "insufficient_field_calibration",
        },
        "agronomic": {},
        "water": {},
    }
    r = compute_field_readiness(state)
    assert r["level"] in ("fair", "poor")
    assert 40 <= r["overall_score"] < 70
    joined = " ".join(r["actionable_ar"])
    assert "صورة" in joined or "NDVI" in joined  # صورة أحدث
    assert "تربة" in joined  # تحليل تربة مفقود
    assert len(r["actionable_ar"]) <= 3


def test_weights_renormalized_when_dims_missing():
    """غياب أبعاد (لا inputs/ثقة/معايرة) ⇒ تُحسب من المتاح فقط (إعادة تسوية)."""
    # متاح فقط: التغطية (available + agronomic = 2/4 = 0.5) ⇒ overall = 50.
    r = compute_field_readiness({"remote_sensing": {"available": True}, "agronomic": {}})
    assert r["dimensions"]["freshness"]["score"] is None
    assert r["dimensions"]["confidence"]["score"] is None
    assert r["dimensions"]["calibration"]["score"] is None
    assert r["dimensions"]["coverage"]["score"] == 0.5
    assert r["overall_score"] == 50.0


def test_empty_state_is_insufficient():
    """حالة فارغة ⇒ تغطية صفر ⇒ insufficient (لا تلفيق جاهزيّة)."""
    r = compute_field_readiness({})
    assert r["overall_score"] == 0.0
    assert r["level"] == "insufficient"
    assert r["dimensions"]["coverage"]["signals_present"] == 0


def test_calibration_insufficient_is_half_not_zero():
    """C5: insufficient_field_calibration نقص مُعلَن لا فشل ⇒ 0.5 (صدق)."""
    cal = compute_field_readiness(
        {
            "remote_sensing": {
                "available": True,
                "calibration_status": "insufficient_field_calibration",
            }
        }
    )["dimensions"]["calibration"]
    assert cal["score"] == 0.5
    full = compute_field_readiness(
        {"remote_sensing": {"available": True, "calibration_status": "calibrated"}}
    )["dimensions"]["calibration"]
    assert full["score"] == 1.0


def test_invalid_input_returns_none():
    """مدخل غير قاموس ⇒ None (fail-safe، صدق)."""
    assert compute_field_readiness(None) is None
    assert compute_field_readiness("nope") is None
