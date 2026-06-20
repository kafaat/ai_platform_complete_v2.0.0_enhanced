"""اختبار تجميع تلخيص حلقة التعلّم (Learning Dashboard data) — نقيّ حتميّ، بلا قاعدة.

يثبت دوالّ التجميع النقيّة في api/learning_summary:
  (أ) لا قرارات/نتائج ⇒ أصفار وsuccess_rate=None (لا تلفيق)؛
  (ب) success_rate صحيحة من outcome_record.success (المحسومة فقط؛ المعلّقة لا تدخل)؛
  (ج) عتبة field_verified (sample_count ≥ العتبة ⇒ field_verified، دونها field_preliminary)؛
  (د) التجميع لكلّ منطقة + إجماليّ، وآخر نشاط = أحدث طابع عبر الجدولين؛
  (هـ) calibrated=False (العتبات تقديريّة). بلا شبكة/قاعدة/ساعة.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.learning_summary import summarize_learning, summarize_region  # noqa: E402


def _ts(day: int) -> datetime:
    return datetime(2026, 6, day, 12, 0, tzinfo=UTC)


def _outcome(region="jawf", success=None, n_eval=1, n_succ=0, flags=None, ts=None):
    """صفّ outcome_record كما يقرؤه الموجِّه (region/success/metrics/created_at)."""
    return {
        "region": region,
        "success": success,
        "metrics": {
            "n_evaluated": n_eval,
            "n_success": n_succ,
            "success_flags": flags or [],
        },
        "created_at": ts,
    }


def _decision(region="jawf", ts=None):
    return {"region": region, "created_at": ts}


# ── (أ) لا قرارات/نتائج ⇒ أصفار، success_rate=None ──


def test_no_data_zeros_and_none_success_rate():
    out = summarize_region("jawf", [], [])
    assert out["decision_count"] == 0
    assert out["outcome_count"] == 0
    assert out["outcomes_decided"] == 0
    assert out["success_rate"] is None  # لا نتيجة محسومة ⇒ لا تُفبرَك
    assert out["sample_count"] == 0
    assert out["evidence_level"] == "none"
    assert out["last_activity_at"] is None
    assert out["calibrated"] is False


def test_summarize_learning_empty_overall_zeros():
    out = summarize_learning([], [])
    assert out["regions"] == []
    assert out["region_count"] == 0
    assert out["overall"]["decision_count"] == 0
    assert out["overall"]["success_rate"] is None
    assert out["calibrated"] is False


# ── (ب) success_rate صحيحة من success (المحسومة فقط؛ المعلّقة لا تدخل) ──


def test_success_rate_from_success_column():
    outcomes = [
        _outcome(success=True),
        _outcome(success=True),
        _outcome(success=True),
        _outcome(success=False),
    ]
    out = summarize_region("jawf", [], outcomes)
    assert out["outcome_count"] == 4
    assert out["outcomes_succeeded"] == 3
    assert out["outcomes_failed"] == 1
    assert out["outcomes_decided"] == 4
    assert out["success_rate"] == 0.75  # 3/4


def test_pending_outcomes_excluded_from_rate():
    # success=None ⇒ معلّقة: تُحصى منفصلةً ولا تدخل بسط/مقام النسبة.
    outcomes = [
        _outcome(success=True),
        _outcome(success=False),
        _outcome(success=None),
        _outcome(success=None),
    ]
    out = summarize_region("jawf", [], outcomes)
    assert out["outcomes_pending"] == 2
    assert out["outcomes_decided"] == 2
    assert out["success_rate"] == 0.5  # 1/2 محسوم — المعلّقة مُستبعَدة


def test_all_pending_success_rate_none():
    outcomes = [_outcome(success=None), _outcome(success=None)]
    out = summarize_region("jawf", [], outcomes)
    assert out["outcomes_pending"] == 2
    assert out["outcomes_decided"] == 0
    assert out["success_rate"] is None  # لا محسوم ⇒ لا تلفيق


# ── (ج) عتبة field_verified ──


def test_field_preliminary_below_threshold():
    # 5 عيّنات (n_evaluated>0) دون عتبة 30 ⇒ field_preliminary.
    outcomes = [_outcome(success=True, n_eval=1) for _ in range(5)]
    out = summarize_region("jawf", [], outcomes)
    assert out["sample_count"] == 5
    assert out["evidence_level"] == "field_preliminary"
    assert out["samples_to_verified"] == out["field_verified_min_samples"] - 5


def test_field_verified_at_threshold():
    n = 30  # عند العتبة بالضبط ⇒ field_verified.
    outcomes = [_outcome(success=True, n_eval=1) for _ in range(n)]
    out = summarize_region("jawf", [], outcomes)
    assert out["sample_count"] == n
    assert out["evidence_level"] == "field_verified"
    assert out["samples_to_verified"] == 0


def test_empty_metrics_not_counted_as_sample():
    # metrics بلا n_evaluated>0 لا تُحتسب عيّنة دليل (لكن تُحصى نتيجةً/نجاحاً).
    outcomes = [_outcome(success=True, n_eval=0)]
    out = summarize_region("jawf", [], outcomes)
    assert out["outcome_count"] == 1
    assert out["outcomes_succeeded"] == 1
    assert out["sample_count"] == 0  # لا عيّنة دليل (لا تضخيم)


# ── (د) تجميع لكلّ منطقة + إجماليّ + آخر نشاط ──


def test_groups_by_region_plus_overall():
    decisions = [_decision("jawf", _ts(1)), _decision("ibb", _ts(2))]
    outcomes = [
        _outcome("jawf", success=True, ts=_ts(3)),
        _outcome("ibb", success=False, ts=_ts(4)),
        _outcome("ibb", success=True, ts=_ts(5)),
    ]
    out = summarize_learning(decisions, outcomes)
    regions = {r["region"]: r for r in out["regions"]}
    assert set(regions) == {"jawf", "ibb"}
    assert regions["jawf"]["decision_count"] == 1
    assert regions["jawf"]["outcome_count"] == 1
    assert regions["jawf"]["success_rate"] == 1.0
    assert regions["ibb"]["outcome_count"] == 2
    assert regions["ibb"]["success_rate"] == 0.5  # 1/2
    # الإجماليّ يجمع كلّ الصفوف.
    assert out["overall"]["decision_count"] == 2
    assert out["overall"]["outcome_count"] == 3
    assert out["overall"]["outcomes_decided"] == 3  # كلّها محسومة


def test_last_activity_is_latest_stamp_across_tables():
    decisions = [_decision("jawf", _ts(2))]
    outcomes = [_outcome("jawf", success=True, ts=_ts(7))]
    out = summarize_region("jawf", decisions, outcomes)
    assert out["last_decision_at"] == _ts(2)
    assert out["last_outcome_at"] == _ts(7)
    assert out["last_activity_at"] == _ts(7)  # الأحدث عبر الجدولين


def test_null_region_grouped_unspecified():
    outcomes = [_outcome(region=None, success=True), _outcome(region="", success=False)]
    out = summarize_learning([], outcomes)
    regions = {r["region"]: r for r in out["regions"]}
    assert "_unspecified" in regions  # NULL/فارغ يُكشَف لا يُخفى
    assert regions["_unspecified"]["outcome_count"] == 2
