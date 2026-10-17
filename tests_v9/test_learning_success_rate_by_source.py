"""REPORT4-LEARNING-SUCCESS-RATE-SOURCE-SPLIT-01 — نسبة نجاح الصفوف المحسومة لكلّ مصدر بمقامه.

``GET /api/v1/learning/summary`` كان يعرض ``overall.success_rate`` وحده: ناجحة ÷ محسومة على صفوف
``outcome_record`` و``recommendation_outcomes`` مجموعةً، فلا يُعرَف مقام كلّ مصدر ولا نسبته.
العقد الإضافيّ ``outcome_reconciliation.success_rate_by_source`` يفصلهما:

  (أ) لكلّ مصدر مقامه (``settled_rows``) وبسطه (``succeeded``) ونسبته — مقامان مختلفان؛
  (ب) غير المحسوم يُستبعَد من المقام ويُعدّ بأسبابه (``unsettled_rows``/``unsettled_by_reason``)؛
  (ج) الحالة المربوطة عبر المصدرين تدخل كلّ مصدر مرّة وتُعلَن في ``linked_overlap``؛
  (د) مقام صفر ⇒ ``success_rate`` = None لا 0؛
  (هـ) النسبة من ``success`` لكلّ صفّ لا من عدّادات الصفوف (``metrics.n_success``)؛
  (و) ``overall`` لم يتغيّر للمستهلكين القائمين (أساس الصفوف المجمَّعة).
نقيّ بلا قاعدة.
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

from api.learning_summary import summarize_learning_with_reconciled_outcomes  # noqa: E402


def _ts(day: int) -> datetime:
    return datetime(2026, 7, day, 12, 0, tzinfo=UTC)


def _or(oid, success, decision_id=None, metrics=None):
    return {
        "outcome_id": oid,
        "field_id": f"fld_{oid}",
        "region": "jawf",
        "decision_id": decision_id,
        "success": success,
        "metrics": metrics or {"n_evaluated": 1, "n_success": 1 if success is True else 0},
        "created_at": _ts(2),
    }


def _ro(oid, *, pred=4.0, act=4.4, accepted=True, matured=True, rec=None):
    return {
        "outcome_id": oid,
        "field_id": f"fld_{oid}",
        "region": "jawf",
        "recommendation_id": rec or f"rec_{oid}",
        "predicted_yield_t_ha": pred,
        "actual_yield_t_ha": act,
        "accepted": accepted,
        "matured_within_lag": matured,
        "outcome_recorded_at": _ts(3),
    }


def _split(out):
    return out["outcome_reconciliation"]["success_rate_by_source"]


def test_each_source_has_its_own_rate_and_denominator():
    out = summarize_learning_with_reconciled_outcomes(
        decision_rows=[],
        outcome_records=[_or("a", True), _or("b", False), _or("c", None)],
        recommendation_outcomes=[
            _ro("r1", act=4.4),  # ناجحة (فعليّ ≥ متوقّع)
            _ro("r2", act=4.1),  # ناجحة
            _ro("r3", act=3.0),  # فاشلة
            _ro("r4", matured=False),  # غير ناضجة ⇒ غير محسومة
            _ro("r5", act=None),  # فعليّ مفقود ⇒ غير محسومة
        ],
    )
    split = _split(out)
    assert split["basis"] == "settled_rows_per_source"
    od = split["sources"]["outcome_record"]
    ro = split["sources"]["recommendation_outcomes"]
    assert (od["rows"], od["settled_rows"], od["succeeded"], od["failed"]) == (3, 2, 1, 1)
    assert od["success_rate"] == 0.5
    assert (ro["rows"], ro["settled_rows"], ro["succeeded"], ro["failed"]) == (5, 3, 2, 1)
    assert ro["success_rate"] == 0.667
    # الإجماليّ القائم لم يتغيّر: يجمع صفوف المصدرين المحسومة (3 ÷ 5).
    assert out["overall"]["outcomes_decided"] == 5
    assert out["overall"]["outcomes_succeeded"] == 3
    assert out["overall"]["success_rate"] == 0.6
    # المجموع بين المصدرين يطابق أساس الصفوف في الإجماليّ (لا مصدر ثالث مخفيّ).
    assert od["settled_rows"] + ro["settled_rows"] == out["overall"]["outcomes_decided"]
    assert od["unsettled_rows"] + ro["unsettled_rows"] == out["overall"]["outcomes_pending"]


def test_missing_values_are_excluded_from_denominator_and_counted_by_reason():
    out = summarize_learning_with_reconciled_outcomes(
        decision_rows=[],
        outcome_records=[_or("a", True), _or("b", None), _or("c", None)],
        recommendation_outcomes=[
            _ro("r1"),
            _ro("r2", pred=None),
            _ro("r3", act=None),
            _ro("r4", act=float("nan")),
            _ro("r5", matured=False),
            _ro("r6", accepted=False),
        ],
    )
    split = _split(out)
    od = split["sources"]["outcome_record"]
    ro = split["sources"]["recommendation_outcomes"]
    assert od["settled_rows"] == 1 and od["success_rate"] == 1.0
    assert od["unsettled_rows"] == 2
    assert od["unsettled_by_reason"] == {"success_missing": 2}
    assert ro["settled_rows"] == 1 and ro["success_rate"] == 1.0
    assert ro["unsettled_rows"] == 5
    assert ro["unsettled_by_reason"] == {
        "missing_prediction": 1,
        "missing_actual": 1,
        "non_finite_value": 1,
        "immature": 1,
        "not_accepted": 1,
    }
    for bucket in (od, ro):
        assert bucket["rows"] == bucket["settled_rows"] + bucket["unsettled_rows"]


def test_linked_outcome_counts_once_in_each_source_and_is_declared_as_overlap():
    out = summarize_learning_with_reconciled_outcomes(
        decision_rows=[],
        outcome_records=[
            _or("a", True, decision_id="dec_1"),  # مربوطة بـro_1 عبر dispatch
            _or("b", True, decision_id="dec_2"),  # صفّان من مصدر واحد للقرار نفسه
            _or("c", False, decision_id="dec_2"),
            _or("d", True, decision_id="dec_3"),  # مربوطة بتوصية غير محسومة
        ],
        recommendation_outcomes=[
            _ro("r1", act=3.0, rec="rec_1"),  # فاشلة — أثر القرار نجح وتوقّع الغلّة لا
            _ro("r3", matured=False, rec="rec_3"),
        ],
        dispatch_links={"rec_1": "dec_1", "rec_3": "dec_3"},
    )
    split = _split(out)
    od = split["sources"]["outcome_record"]
    ro = split["sources"]["recommendation_outcomes"]
    # كلّ مصدر يحسب صفّه المربوط مرّة واحدة في مقامه — لا طرح ولا مضاعفة داخل المصدر.
    assert (od["settled_rows"], od["succeeded"], od["success_rate"]) == (4, 3, 0.75)
    assert (ro["settled_rows"], ro["succeeded"], ro["success_rate"]) == (1, 0, 0.0)
    overlap = split["linked_overlap"]
    assert overlap["cases"] == 2  # dec_1 وdec_3 فقط؛ dec_2 مجموعة مصدر واحد ليست تداخلاً
    assert overlap["rows_by_source"] == {"outcome_record": 2, "recommendation_outcomes": 2}
    assert overlap["settled_in_both_sources"] == 1  # dec_1 فقط محسومة في المصدرين
    assert overlap["counted_in_each_source"] is True


def test_zero_denominator_yields_none_not_zero():
    out = summarize_learning_with_reconciled_outcomes(
        decision_rows=[],
        outcome_records=[_or("a", None), _or("b", None)],
        recommendation_outcomes=[],
    )
    split = _split(out)
    od = split["sources"]["outcome_record"]
    ro = split["sources"]["recommendation_outcomes"]
    assert od["settled_rows"] == 0 and od["success_rate"] is None
    assert od["unsettled_rows"] == 2
    assert ro["rows"] == 0 and ro["settled_rows"] == 0 and ro["success_rate"] is None
    assert out["overall"]["success_rate"] is None


def test_rate_comes_from_each_row_success_not_from_row_counters():
    """``metrics`` يزعم 3/3 نجاحاً، لكنّ عمود ``success`` = False — النسبة تتبع العمود."""
    out = summarize_learning_with_reconciled_outcomes(
        decision_rows=[],
        outcome_records=[_or("a", False, metrics={"n_evaluated": 3, "n_success": 3})],
        recommendation_outcomes=[],
    )
    od = _split(out)["sources"]["outcome_record"]
    assert od["success_rate"] == 0.0
    assert (od["succeeded"], od["failed"]) == (0, 1)


def test_empty_input_still_declares_both_sources():
    from core.outcome_reconciler import SOURCE_MODELS, settled_success_by_source

    split = settled_success_by_source([])
    assert tuple(split["sources"]) == SOURCE_MODELS
    for bucket in split["sources"].values():
        assert bucket["rows"] == 0 and bucket["success_rate"] is None
    assert split["linked_overlap"]["cases"] == 0
