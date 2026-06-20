"""اختبارات نقيّة لطبقة تشكيل إعادة تشغيل الموسم (api.agronomic_replay).

دمج سلاسل مُدامة في خطّ زمنيّ واحد مرتّب تصاعديّاً: حدث بلا تاريخ يُهمَل، المسار
الفارغ يُعلَن صفراً، المدى من البيانات فقط — لا تلفيق.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.agronomic_replay import build_agronomic_replay  # noqa: E402


def test_merges_tracks_sorted_ascending():
    out = build_agronomic_replay(
        "f1",
        ndvi=[{"acquisition_date": "2026-03-01", "ndvi_mean": 0.62}],
        decisions=[
            {"created_at": "2026-02-15", "decision_type": "irrigation_plan", "decision_id": "dec_1"}
        ],
        outcomes=[{"created_at": "2026-04-10", "success": True, "outcome_id": "out_1"}],
    )
    dates = [e["date"] for e in out["events"]]
    assert dates == sorted(dates)  # تصاعديّ
    assert dates[0].startswith("2026-02-15")  # القرار أوّلاً
    tracks = [e["track"] for e in out["events"]]
    assert tracks == ["decision", "ndvi", "outcome"]
    assert out["counts_by_track"]["ndvi"] == 1
    assert out["span"] == {"start": dates[0], "end": dates[-1]}


def test_event_without_date_is_dropped():
    # حدث بلا تاريخ ⇒ يُهمَل (لا حدث بلا زمن، لا تلفيق).
    out = build_agronomic_replay(
        "f1",
        ndvi=[{"ndvi_mean": 0.5}, {"acquisition_date": "2026-03-01", "ndvi_mean": 0.6}],
    )
    assert out["event_count"] == 1
    assert out["counts_by_track"]["ndvi"] == 1


def test_empty_tracks_declared_zero_no_span():
    out = build_agronomic_replay("f1")
    assert out["event_count"] == 0
    assert out["span"] is None
    assert out["counts_by_track"] == {
        "ndvi": 0,
        "weather": 0,
        "irrigation": 0,
        "decision": 0,
        "outcome": 0,
    }
    assert out["provenance"]["calibrated"] == "not_applicable"


def test_outcome_success_labeling():
    out = build_agronomic_replay(
        "f1",
        outcomes=[
            {"created_at": "2026-01-01", "success": True, "outcome_id": "o1"},
            {"created_at": "2026-01-02", "success": False, "outcome_id": "o2"},
            {"created_at": "2026-01-03", "success": None, "outcome_id": "o3"},
        ],
    )
    labels = [e["label_ar"] for e in out["events"]]
    assert labels == ["نتيجة: نجاح", "نتيجة: إخفاق", "نتيجة مُقاسة"]


def test_ndvi_value_carried_and_iso_datetime_normalized():
    from datetime import UTC, datetime

    dt = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    out = build_agronomic_replay(
        "f1",
        irrigation=[{"last_run_at": dt, "name": "جدول صباحيّ", "schedule_id": "s1"}],
        ndvi=[{"acquisition_date": "2026-05-02", "ndvi_mean": 0.7}],
    )
    irr = next(e for e in out["events"] if e["track"] == "irrigation")
    assert irr["date"] == dt.isoformat()  # datetime → ISO
    assert irr["ref_id"] == "s1"
    nd = next(e for e in out["events"] if e["track"] == "ndvi")
    assert nd["value"] == 0.7


def test_field_id_and_tracks_metadata():
    out = build_agronomic_replay("field_07", generated_at="2026-06-20T12:00:00+00:00")
    assert out["field_id"] == "field_07"
    assert out["generated_at"] == "2026-06-20T12:00:00+00:00"
    assert [t["track"] for t in out["tracks"]] == [
        "ndvi",
        "weather",
        "irrigation",
        "decision",
        "outcome",
    ]
