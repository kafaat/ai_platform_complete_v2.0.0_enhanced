"""اختبارات سجلّ التنفيذ (core.execution_ledger_entry) — المرحلة A، الشريحة 4.

نقيّة وحتميّة ⇒ `unit`. تثبّت: تطبيع النتيجة (executed/failed فقط، fail-closed)، حتميّة
content_hash وحساسيّته للمحتوى، بناء القيد من صفّ قرار (dict/كائن)، وقابليّة التحقّق.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.execution_ledger_entry import (  # noqa: E402
    OUTCOMES,
    build_ledger_entry,
    compute_ledger_hash,
    normalize_outcome,
)


# ── تطبيع النتيجة ──
def test_outcomes_constant():
    assert OUTCOMES == ("executed", "failed")


def test_normalize_outcome_accepts_known():
    assert normalize_outcome("executed") == "executed"
    assert normalize_outcome("FAILED") == "failed"
    assert normalize_outcome(" executed ") == "executed"


def test_normalize_outcome_rejects_unknown():
    with pytest.raises(ValueError, match="مجهولة"):
        normalize_outcome("queued")
    with pytest.raises(ValueError, match="مجهولة"):
        normalize_outcome("")


# ── بصمة المحتوى ──
def test_hash_is_deterministic():
    a = compute_ledger_hash("disp_1", "executed", "2026-06-16T12:00:00+00:00", {"water_mm": 18})
    b = compute_ledger_hash("disp_1", "executed", "2026-06-16T12:00:00+00:00", {"water_mm": 18})
    assert a == b
    assert len(a) == 64  # SHA-256 hex


def test_hash_is_order_independent_for_detail():
    a = compute_ledger_hash("d", "executed", "t", {"x": 1, "y": 2})
    b = compute_ledger_hash("d", "executed", "t", {"y": 2, "x": 1})
    assert a == b


def test_hash_sensitive_to_content():
    base = compute_ledger_hash("d", "executed", "t", {"x": 1})
    assert compute_ledger_hash("d", "failed", "t", {"x": 1}) != base
    assert compute_ledger_hash("d2", "executed", "t", {"x": 1}) != base
    assert compute_ledger_hash("d", "executed", "t2", {"x": 1}) != base
    assert compute_ledger_hash("d", "executed", "t", {"x": 2}) != base


# ── بناء القيد ──
def _row(**kw):
    base = {
        "decision_id": "disp_abc",
        "action_type": "irrigation",
        "field_id": "f1",
    }
    base.update(kw)
    return base


def test_build_ledger_entry_basic():
    e = build_ledger_entry(
        _row(),
        outcome="executed",
        recorded_at="2026-06-16T12:00:00+00:00",
        channel="SMS",
        note_ar="نُفِّذ بنجاح",
        detail={"water_mm": 18.0},
    )
    assert e["decision_id"] == "disp_abc"
    assert e["action_type"] == "irrigation"
    assert e["field_id"] == "f1"
    assert e["channel"] == "sms"  # مُطبّع
    assert e["outcome"] == "executed"
    assert e["note_ar"] == "نُفِّذ بنجاح"
    assert e["detail"] == {"water_mm": 18.0}
    assert len(e["content_hash"]) == 64
    # البصمة قابلة للتحقّق (إعادة الحساب من القيد)
    assert e["content_hash"] == compute_ledger_hash(
        "disp_abc", "executed", "2026-06-16T12:00:00+00:00", {"water_mm": 18.0}
    )


def test_build_ledger_entry_rejects_bad_outcome():
    with pytest.raises(ValueError, match="مجهولة"):
        build_ledger_entry(_row(), outcome="maybe", recorded_at="t")


def test_build_ledger_entry_defaults():
    e = build_ledger_entry(_row(), outcome="failed", recorded_at="t")
    assert e["channel"] is None
    assert e["note_ar"] == ""
    assert e["detail"] == {}
    assert e["outcome"] == "failed"


def test_build_ledger_entry_reads_object_row():
    class Row:
        decision_id = "disp_o"
        action_type = "spray"
        field_id = None

        def __getitem__(self, k):
            return getattr(self, k)

    e = build_ledger_entry(Row(), outcome="executed", recorded_at="t")
    assert e["decision_id"] == "disp_o"
    assert e["field_id"] is None
