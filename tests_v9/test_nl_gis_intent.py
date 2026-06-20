"""اختبارات نقيّة لمُحلّل نيّة NL-GIS (api.nl_gis_intent).

تصنيف حتميّ لقائمة نيّات مغلقة + استخلاص خانات من النصّ فقط (لا تلفيق)، ورفض
صريح لما هو خارج القائمة (لا تخمين، لا SQL حُرّ).
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.nl_gis_intent import SUPPORTED_INTENTS, parse_nl_intent  # noqa: E402


def test_ndvi_drop_with_explicit_threshold():
    out = parse_nl_intent("اعرض الحقول التي انخفض NDVI فيها أكثر من 15%")
    assert out["intent"] == "ndvi_drop"
    assert out["supported"] is True
    assert out["slots"]["threshold_pct"] == 15.0
    assert out["slots"]["threshold_is_default"] is False


def test_ndvi_drop_default_threshold_when_unspecified():
    # ذكر NDVI وانخفاض بلا رقم ⇒ عتبة افتراضيّة مُوثَّقة (موسومة default، لا مُختلقة).
    out = parse_nl_intent("ما الحقول التي تراجع فيها مؤشّر الغطاء النباتي؟")
    assert out["intent"] == "ndvi_drop"
    assert out["slots"]["threshold_pct"] == 15.0
    assert out["slots"]["threshold_is_default"] is True


def test_alert_filter_crop_region_and_type():
    out = parse_nl_intent("اعرض حقول القمح في الجوف التي لديها تنبيه حرارة")
    assert out["intent"] == "alert_filter"
    assert out["slots"]["crop"] == "قمح"
    assert out["slots"]["region"] == "الجوف"
    assert out["slots"]["alert_type"] == "heat_stress"
    assert out["confidence"] > 0.8  # ثلاثة مُرشِّحات ⇒ ثقة عالية


def test_alert_filter_type_only_no_crop_region():
    out = parse_nl_intent("أظهر التنبيهات النشطة عن خطر المرض")
    assert out["intent"] == "alert_filter"
    assert out["slots"]["alert_type"] == "disease_risk"
    assert out["slots"]["crop"] is None
    assert out["slots"]["region"] is None


def test_irrigation_gap_with_days():
    out = parse_nl_intent("اعرض الحقول التي لم تُروَ منذ 5 أيّام")
    assert out["intent"] == "irrigation_gap"
    assert out["slots"]["days"] == 5
    assert out["slots"]["days_is_default"] is False


def test_irrigation_gap_default_days():
    # ريّ + «لم» بلا رقم ⇒ فجوة افتراضيّة مُوثَّقة.
    out = parse_nl_intent("ما الحقول التي لم تُسقَ مؤخّراً؟")
    assert out["intent"] == "irrigation_gap"
    assert out["slots"]["days"] == 5
    assert out["slots"]["days_is_default"] is True


def test_unsupported_query_is_rejected_with_reason():
    # طلب خارج القائمة ⇒ unsupported صريح (لا تخمين، لا تنفيذ).
    out = parse_nl_intent("احذف الحقل رقم 3 وأنشئ حقلاً جديداً")
    assert out["intent"] == "unsupported"
    assert out["supported"] is False
    assert out["reason_ar"]
    assert out["confidence"] == 0.0


def test_empty_query_is_unsupported():
    out = parse_nl_intent("   ")
    assert out["intent"] == "unsupported"
    assert out["supported"] is False


def test_supported_intents_whitelist_excludes_unsupported():
    assert "unsupported" not in SUPPORTED_INTENTS
    assert SUPPORTED_INTENTS == {"ndvi_drop", "alert_filter", "irrigation_gap"}


def test_intent_never_returns_sql_or_freeform():
    # ضمان أمنيّ: المخرجات خانات مُقيَّدة فقط — لا مفتاح يحمل SQL/جملة حُرّة.
    out = parse_nl_intent("اعرض حقول الطماطم التي لديها تنبيه رطوبة")
    assert set(out.keys()) <= {"intent", "slots", "confidence", "supported", "reason_ar"}
    assert "sql" not in out and "query" not in out
    assert out["slots"]["alert_type"] == "low_moisture"
    assert out["slots"]["crop"] == "طماطم"
