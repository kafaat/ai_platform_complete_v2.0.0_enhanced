"""اختبار إدامة الدليل (Evidence Persistence — P0-2) — الجزء النقيّ.

يثبت أنّ evidence_from_persisted_outcomes يبني الدليل التراكميّ من صفوف outcome_record
المُدامة (metrics + created_at) بإعادة استخدام منطق aggregate_evidence نفسه (لا عتبة
مكرّرة). مسار قراءة القاعدة تكامليّ (يتطلّب Postgres) — هنا نتحقّق من المنطق فقط، نقيّاً.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.evidence_registry import (  # noqa: E402
    _FIELD_VERIFIED_MIN_SAMPLES,
    evidence_from_persisted_outcomes,
)


def _row(n_eval, n_success, flags=None, at="2026-06-20T10:00:00"):
    """صفّ outcome_record مُدام مُصطنَع: metrics (مخرجات measure_outcome) + created_at."""
    return {
        "metrics": {
            "n_evaluated": n_eval,
            "n_success": n_success,
            "success_flags": flags or [],
        },
        "created_at": at,
    }


def test_empty_persisted_is_no_evidence():
    """لا صفوف مُدامة ⇒ دليل none (أو expert_opinion إن خبير) — لا تضخيم."""
    out = evidence_from_persisted_outcomes("ibb", [])
    assert out["sample_count"] == 0
    assert out["evidence_level"] == "none"
    assert out["source"] == "persisted_outcomes"
    assert out["persisted_rows"] == 0


def test_empty_metrics_not_counted_as_sample():
    """صفّ بلا مقياس مُقيَّم (n_evaluated=0) لا يُحتسب عيّنة (صدق: لا دليل مُضخَّم)."""
    rows = [_row(0, 0), _row(2, 1, ["irrigation_followed"])]
    out = evidence_from_persisted_outcomes("ibb", rows)
    assert out["sample_count"] == 1  # الصفّ الفارغ أُسقِط
    assert out["persisted_rows"] == 2  # لكن كلا الصفّين قُرِئا
    assert out["success_rate"] == 0.5  # 1/2 مقياس ناجح


def test_preliminary_below_threshold():
    """عيّنات تحت العتبة ⇒ field_preliminary + عدّ ما يلزم للتحقّق."""
    rows = [_row(1, 1, ["stress_avoided"]) for _ in range(5)]
    out = evidence_from_persisted_outcomes("tihama", rows)
    assert out["sample_count"] == 5
    assert out["evidence_level"] == "field_preliminary"
    assert out["samples_to_verified"] == _FIELD_VERIFIED_MIN_SAMPLES - 5
    assert out["success_flag_counts"]["stress_avoided"] == 5


def test_verified_at_threshold():
    """عيّنات ≥ العتبة ⇒ field_verified (الدليل تراكَم من نتائج مُدامة)."""
    rows = [_row(1, 1) for _ in range(_FIELD_VERIFIED_MIN_SAMPLES)]
    out = evidence_from_persisted_outcomes("marib", rows)
    assert out["sample_count"] == _FIELD_VERIFIED_MIN_SAMPLES
    assert out["evidence_level"] == "field_verified"
    assert out["samples_to_verified"] == 0


def test_last_evaluated_from_created_at():
    """آخر تقييم = أحدث created_at عبر الصفوف المُدامة (نَسَب زمنيّ صادق)."""
    rows = [
        _row(1, 1, at="2026-06-18T09:00:00"),
        _row(1, 0, at="2026-06-20T09:00:00"),
    ]
    out = evidence_from_persisted_outcomes("jawf", rows)
    assert out["last_evaluated_at"] == "2026-06-20T09:00:00"
    assert out["success_rate"] == 0.5
