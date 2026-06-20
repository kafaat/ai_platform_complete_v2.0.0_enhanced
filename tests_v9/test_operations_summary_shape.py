"""اختبارات نقيّة لطبقة تشكيل تلخيص العمليّات (api.operations_summary).

منطق صرف بلا قاعدة: عدّ كامل ⇒ إجماليّات صحيحة + تصنيف خطورة، غياب مصدر ⇒
0/None + note_ar صريح (لا تلفيق)، وعلم calibrated=not_applicable دائماً.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.operations_summary import shape_operations_summary  # noqa: E402


def test_full_counts_yield_totals_and_severity():
    out = shape_operations_summary(
        {
            "fields": 8,
            "alerts_active": {"info": 2, "warning": 3, "critical": 1},
            "equipment": 5,
            "iot_devices": 12,
            "decision_records": 7,
            "irrigation_valves": 4,
            "irrigation_schedules": 2,
            "last_activity_at": "2026-06-20T10:00:00+00:00",
        }
    )
    assert out["totals"]["fields"] == 8
    assert out["totals"]["equipment"] == 5
    assert out["totals"]["iot_devices"] == 12
    assert out["totals"]["decision_records"] == 7
    assert out["totals"]["active_alerts"] == 6  # 2+3+1
    assert out["alerts"]["by_severity"] == {"info": 2, "warning": 3, "critical": 1}
    assert out["alerts"]["active_total"] == 6
    assert out["alerts"]["available"] is True
    assert out["irrigation"] == {"valves": 4, "schedules": 2, "available": True}
    assert out["last_activity_at"] == "2026-06-20T10:00:00+00:00"
    # عدّ تجميعيّ ⇒ لا معايرة، ولا ملاحظة غياب (كلّ المصادر حاضرة).
    assert out["provenance"]["calibrated"] == "not_applicable"
    assert "note_ar" not in out["provenance"]


def test_missing_sources_produce_zero_none_and_note():
    out = shape_operations_summary(
        {
            "fields": None,
            "alerts_active": None,
            "equipment": None,
            "iot_devices": None,
            "decision_records": None,
            "irrigation_valves": None,
            "irrigation_schedules": None,
            "last_activity_at": None,
        }
    )
    # غياب مصدر ⇒ 0 في الإجماليّات (لا تلفيق، صفر صادق).
    assert out["totals"] == {
        "fields": 0,
        "equipment": 0,
        "iot_devices": 0,
        "decision_records": 0,
        "active_alerts": 0,
    }
    assert out["alerts"]["available"] is False
    assert out["alerts"]["by_severity"] == {"info": 0, "warning": 0, "critical": 0}
    assert out["irrigation"]["available"] is False
    assert out["last_activity_at"] is None
    # note_ar صريح يذكر كلّ المصادر الغائبة.
    note = out["provenance"]["note_ar"]
    for src in ("fields", "alerts", "equipment", "iot_devices", "decision_records"):
        assert src in note


def test_empty_counts_dict_is_safe():
    # قاموس فارغ كليّاً ⇒ كلّ شيء غائب، لا انهيار.
    out = shape_operations_summary({})
    assert out["totals"]["fields"] == 0
    assert out["alerts"]["available"] is False
    assert "note_ar" in out["provenance"]


def test_partial_severity_fills_missing_keys_with_zero():
    # خطورة جزئيّة (critical فقط) ⇒ بقيّة المفاتيح 0 وليست غائبة.
    out = shape_operations_summary({"alerts_active": {"critical": 4}})
    assert out["alerts"]["by_severity"] == {"info": 0, "warning": 0, "critical": 4}
    assert out["alerts"]["active_total"] == 4
    assert out["alerts"]["available"] is True


def test_severity_only_unavailable_when_alerts_dict_none():
    # حضور بقيّة المصادر مع غياب alerts فقط ⇒ note يذكر alerts وحده.
    out = shape_operations_summary(
        {
            "fields": 3,
            "alerts_active": None,
            "equipment": 1,
            "iot_devices": 0,
            "decision_records": 2,
            "irrigation_valves": 0,
            "irrigation_schedules": 0,
        }
    )
    assert "alerts" in out["provenance"]["note_ar"]
    assert "fields" not in out["provenance"]["note_ar"]
    assert out["irrigation"]["available"] is True  # 0 موجود (لا None)


def test_sections_status_and_partial_all_ok():
    """كلّ المصادر حاضرة ⇒ كلّ قسم status=ok (freshness حيّ)، partial=False، generated_at مُمرَّر."""
    out = shape_operations_summary(
        {
            "fields": 1,
            "alerts_active": {"info": 0, "warning": 0, "critical": 0},
            "equipment": 1,
            "iot_devices": 1,
            "decision_records": 1,
            "irrigation_valves": 1,
            "irrigation_schedules": 1,
        },
        generated_at="2026-06-20T12:00:00+00:00",
    )
    assert out["generated_at"] == "2026-06-20T12:00:00+00:00"
    assert out["partial"] is False
    for sec in ("fields", "alerts", "equipment", "iot_devices", "decision_records", "irrigation"):
        assert out["sections"][sec]["status"] == "ok"
        assert out["sections"][sec]["freshness_sec"] == 0


def test_sections_unavailable_marks_partial_with_reason():
    """قسم بمصدر غائب ⇒ status=unavailable + سبب، و partial=True (صدق التشغيل)."""
    out = shape_operations_summary({"fields": 3, "equipment": None})
    assert out["partial"] is True
    assert out["sections"]["fields"]["status"] == "ok"
    assert out["sections"]["equipment"]["status"] == "unavailable"
    assert out["sections"]["equipment"]["error"]  # سبب صريح غير فارغ


def test_section_error_yields_degraded():
    """مصدر متاح مع خطأ مُمرَّر ⇒ degraded (بيانات جزئيّة)، لا unavailable."""
    out = shape_operations_summary({"fields": 3}, errors={"fields": "بطء في القاعدة"})
    assert out["sections"]["fields"]["status"] == "degraded"
    assert out["sections"]["fields"]["error"] == "بطء في القاعدة"
    assert out["partial"] is True


def test_negative_or_bad_count_coerced_safely():
    # قيم شاذّة (سالب/نصّ) ⇒ 0 لا انهيار (حارس _as_count).
    out = shape_operations_summary({"fields": -5, "equipment": "x", "iot_devices": 3})
    assert out["totals"]["fields"] == 0
    # equipment نصّ غير رقميّ ⇒ يُعامَل None ⇒ 0 + يُوسَم غائباً.
    assert out["totals"]["equipment"] == 0
    assert out["totals"]["iot_devices"] == 3
    assert "equipment" in out["provenance"]["note_ar"]
