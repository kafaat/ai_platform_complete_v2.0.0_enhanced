"""
tests_v9/test_harvest_traceability_v65.py — منطق تتبّع سلسلة الإمداد (نقيّ، بلا DB).

يغطّي محرّك core/engines/harvest_traceability:
  ① compute_event_hash حتميّ ومستقلّ عن ترتيب مفاتيح details، ويتغيّر بتغيّر المحتوى.
  ② status_for_event يشتقّ حالة الدفعة من نوع الحدث (والفحص لا يحرّكها).
  ③ assemble_traceability يرتّب السلسلة زمنيّاً حتميّاً ويقيّم الاكتمال (حصاد→بيع).
"""

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))


def test_event_hash_deterministic_and_key_order_independent():
    """نفس المحتوى ⇒ نفس البصمة، بصرف النظر عن ترتيب مفاتيح details."""
    from core.engines.harvest_traceability import compute_event_hash

    h1 = compute_event_hash("hl_1", "storage", "2026-03-01T10:00:00", {"a": 1, "b": 2})
    h2 = compute_event_hash("hl_1", "storage", "2026-03-01T10:00:00", {"b": 2, "a": 1})
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_event_hash_changes_with_content():
    """تغيّر أيّ مكوّن (الوقت/النوع/التفاصيل) ⇒ بصمة مختلفة (كشف التلاعب)."""
    from core.engines.harvest_traceability import compute_event_hash

    base = compute_event_hash("hl_1", "storage", "2026-03-01T10:00:00", {"temp": 18})
    assert base != compute_event_hash("hl_1", "storage", "2026-03-01T11:00:00", {"temp": 18})
    assert base != compute_event_hash("hl_1", "transport", "2026-03-01T10:00:00", {"temp": 18})
    assert base != compute_event_hash("hl_1", "storage", "2026-03-01T10:00:00", {"temp": 20})


def test_status_for_event_transitions():
    """نوع الحدث يشتقّ حالة الدفعة؛ فحص الجودة لا يحرّكها؛ المجهول يُبقيها."""
    from core.engines.harvest_traceability import status_for_event

    assert status_for_event("harvest", "harvested") == "harvested"
    assert status_for_event("storage", "harvested") == "stored"
    assert status_for_event("transport", "stored") == "in_transit"
    assert status_for_event("sales", "in_transit") == "sold"
    # فحص الجودة لا يغيّر موضع الدفعة.
    assert status_for_event("quality_check", "stored") == "stored"
    # نوع غير محرِّك/مجهول ⇒ تبقى الحالة.
    assert status_for_event("unknown", "in_transit") == "in_transit"


def test_assemble_orders_chain_deterministically():
    """السلسلة تُرتَّب بـ(occurred_at, custody_event_id) مهما كان ترتيب الإدخال."""
    from core.engines.harvest_traceability import assemble_traceability

    events = [
        {"custody_event_id": 3, "event_type": "transport", "occurred_at": "2026-03-02T07:00:00"},
        {"custody_event_id": 1, "event_type": "harvest", "occurred_at": "2026-03-01T08:00:00"},
        {"custody_event_id": 2, "event_type": "storage", "occurred_at": "2026-03-01T12:00:00"},
    ]
    out = assemble_traceability({"harvest_lot_id": "hl_1"}, list(reversed(events)))
    types = [e["event_type"] for e in out["custody_chain"]]
    assert types == ["harvest", "storage", "transport"]
    assert out["chain"]["event_count"] == 3


def test_assemble_completeness_harvest_to_market():
    """«كامل» = بدأت بحصاد وبلغت بيعاً."""
    from core.engines.harvest_traceability import assemble_traceability

    partial = assemble_traceability(
        {"harvest_lot_id": "hl_1"},
        [{"custody_event_id": 1, "event_type": "harvest", "occurred_at": "2026-03-01T08:00:00"}],
    )
    assert partial["chain"]["started_at_harvest"] is True
    assert partial["chain"]["reached_market"] is False
    assert partial["chain"]["complete"] is False

    full = assemble_traceability(
        {"harvest_lot_id": "hl_1"},
        [
            {"custody_event_id": 1, "event_type": "harvest", "occurred_at": "2026-03-01T08:00:00"},
            {"custody_event_id": 2, "event_type": "sales", "occurred_at": "2026-03-03T14:00:00"},
        ],
        origin={"field_id": "f1", "field_name": "حقل وادي سبأ"},
    )
    assert full["chain"]["complete"] is True
    assert full["origin"]["field_name"] == "حقل وادي سبأ"


def test_event_type_and_role_constants_match_schema():
    """ثوابت الأنواع/الأدوار تطابق قيود CHECK في v65 (مصدر حقيقة واحد)."""
    from core.engines.harvest_traceability import CUSTODY_EVENT_TYPES, HANDLER_ROLES, LOT_STATUSES

    assert set(CUSTODY_EVENT_TYPES) == {"harvest", "storage", "quality_check", "transport", "sales"}
    assert "farmer" in HANDLER_ROLES and "buyer" in HANDLER_ROLES
    assert "harvested" in LOT_STATUSES and "sold" in LOT_STATUSES


if __name__ == "__main__":
    test_event_hash_deterministic_and_key_order_independent()
    test_event_hash_changes_with_content()
    test_status_for_event_transitions()
    test_assemble_orders_chain_deterministically()
    test_assemble_completeness_harvest_to_market()
    test_event_type_and_role_constants_match_schema()
    print("✓ كل اختبارات تتبّع سلسلة الإمداد (v65) نجحت")
