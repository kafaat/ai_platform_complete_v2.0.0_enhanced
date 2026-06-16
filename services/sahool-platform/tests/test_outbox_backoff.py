"""اختبارات نقيّة (unit) لتصليب الـoutbox: التراجع الأسّيّ + تشكيل ملخّص DLQ.

لا قاعدة بيانات ولا خدمات — منطق صرف فقط (دالّة backoff النقيّة + شكل DLQ).
الـSELECT/requeue الفعليّان تكامليّان (يحتاجان Postgres) ولا يُختبران هنا.
"""

import pytest
from api.event_bus import (
    OUTBOX_BACKOFF_BASE_SECONDS,
    OUTBOX_BACKOFF_MAX_SECONDS,
    dead_letter_summary,
    outbox_backoff_seconds,
)

pytestmark = pytest.mark.unit


def test_backoff_base_case_retry_zero():
    # retry_count=0 ⇒ base * 2**0 = base
    assert outbox_backoff_seconds(0) == OUTBOX_BACKOFF_BASE_SECONDS
    assert outbox_backoff_seconds(0, base=2.0) == 2.0


def test_backoff_doubles_each_step():
    assert outbox_backoff_seconds(1) == 4.0
    assert outbox_backoff_seconds(2) == 8.0
    assert outbox_backoff_seconds(3) == 16.0
    assert outbox_backoff_seconds(4) == 32.0


def test_backoff_monotonic_increasing_until_cap():
    prev = -1.0
    for rc in range(0, 12):  # حتى ما قبل بلوغ السقف
        cur = outbox_backoff_seconds(rc)
        assert cur >= prev, f"backoff تراجع عند retry_count={rc}"
        prev = cur


def test_backoff_capped_at_max():
    # قِيَم كبيرة جداً تُقصّ إلى السقف (ساعة)
    assert outbox_backoff_seconds(50) == OUTBOX_BACKOFF_MAX_SECONDS
    assert outbox_backoff_seconds(1000) == OUTBOX_BACKOFF_MAX_SECONDS
    # لا شيء يتجاوز السقف أبداً
    for rc in range(0, 200):
        assert outbox_backoff_seconds(rc) <= OUTBOX_BACKOFF_MAX_SECONDS


def test_backoff_negative_treated_as_zero():
    assert outbox_backoff_seconds(-5) == outbox_backoff_seconds(0)


def test_backoff_custom_base_and_cap():
    assert outbox_backoff_seconds(3, base=1.0, cap=100.0) == 8.0
    assert outbox_backoff_seconds(10, base=1.0, cap=100.0) == 100.0  # مقصوص


# ─── تشكيل ملخّص DLQ (نقيّ) ──────────────────────────────────────


def test_dead_letter_summary_empty():
    out = dead_letter_summary([])
    assert out == {"total": 0, "sample": []}
    assert dead_letter_summary(None) == {"total": 0, "sample": []}


def test_dead_letter_summary_shapes_rows():
    rows = [
        {
            "outbox_id": 7,
            "event_id": "abc-123",
            "nats_subject": "sahool.events.field.created",
            "retry_count": 5,
            "last_error": "ConnectionError: boom",
            "last_attempt_at": None,
        }
    ]
    out = dead_letter_summary(rows)
    assert out["total"] == 1
    item = out["sample"][0]
    assert item["outbox_id"] == 7
    assert item["event_id"] == "abc-123"
    assert item["nats_subject"] == "sahool.events.field.created"
    assert item["retry_count"] == 5
    assert item["last_error"] == "ConnectionError: boom"
    assert item["last_attempt_at"] is None


def test_dead_letter_summary_isoformats_datetime():
    import datetime

    ts = datetime.datetime(2026, 6, 16, 12, 0, 0)
    out = dead_letter_summary([{"outbox_id": 1, "event_id": None, "last_attempt_at": ts}])
    assert out["sample"][0]["last_attempt_at"] == ts.isoformat()
    assert out["sample"][0]["event_id"] is None


def test_dead_letter_summary_sample_capped_total_accurate():
    rows = [{"outbox_id": i, "event_id": str(i)} for i in range(120)]
    out = dead_letter_summary(rows)
    assert out["total"] == 120  # العدّ كامل
    assert len(out["sample"]) == 50  # العيّنة مقصوصة
