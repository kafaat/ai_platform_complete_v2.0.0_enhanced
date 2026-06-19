"""اختبار الخطّ الزمنيّ الموحّد للحقل (MVP): منطق الدمج النقيّ.

نقطة ``GET /api/v1/fields/{id}/unified-timeline`` تجلب أحداث الحقل عبر كلّ أنواع
الكيانات (entity_id أو payload->>'field_id') وتمرّرها لـ``assemble_timeline``. هنا
نختبر المنطق النقيّ الذي تعتمده النقطة: دمج مصادر مختلفة + فرز + تصنيف + ترشيح.
نواة بلا قاعدة.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.field_timeline import assemble_timeline  # noqa: E402


def _mixed_events() -> list[dict]:
    # يحاكي ما يُعيده استعلام الدمج: أحداث من أنواع كيانات مختلفة لنفس الحقل.
    return [
        {"event_type": "field.created", "occurred_at": "2026-06-01T08:00:00+00:00", "payload": {}},
        {
            "event_type": "lifecycle.transitioned",
            "occurred_at": "2026-06-03T08:00:00+00:00",
            "payload": {"field_id": "F1"},
        },
        {
            "event_type": "operation.irrigation.completed",
            "occurred_at": "2026-06-05T08:00:00+00:00",
            "payload": {"field_id": "F1"},
        },
        {
            "event_type": "alert.created",
            "occurred_at": "2026-06-04T08:00:00+00:00",
            "payload": {"field_id": "F1", "severity": "high"},
        },
        {
            "event_type": "recommendation.created",
            "occurred_at": "2026-06-06T08:00:00+00:00",
            "payload": {"field_id": "F1"},
        },
    ]


def test_merges_all_entity_types():
    tl = assemble_timeline("F1", _mixed_events()).to_dict()
    # كلّ المصادر (دورة حياة + انتقال + عمليّة + تنبيه + توصية) تظهر.
    assert tl["total_events"] == 5
    types = {e["event_type"] for e in tl["events"]}
    assert {"field.created", "alert.created", "recommendation.created"} <= types


def test_sorted_newest_first_and_oldest():
    desc = assemble_timeline("F1", _mixed_events(), newest_first=True).to_dict()
    assert desc["events"][0]["event_type"] == "recommendation.created"  # 06-06 الأحدث
    asc = assemble_timeline("F1", _mixed_events(), newest_first=False).to_dict()
    assert asc["events"][0]["event_type"] == "field.created"  # 06-01 الأقدم


def test_category_filter():
    tl = assemble_timeline("F1", _mixed_events(), category_filter=["operation"]).to_dict()
    assert tl["total_events"] == 1
    assert tl["events"][0]["event_type"] == "operation.irrigation.completed"
    assert all(e["category"] == "operation" for e in tl["events"])
