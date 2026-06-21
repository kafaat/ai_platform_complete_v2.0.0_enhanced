"""اختبارات نقيّة لرصد حلقة التنفيذ (api.execution_feedback).

تصنيف حالة الحلقة من سجلّات مُدامة فقط: لا قيد تنفيذ ⇒ unknown، لا نتيجة ⇒ unmeasured
(لا افتراض نجاح)، فشل ⇒ failed — رصد قراءة فقط، لا تلفيق.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.execution_feedback import classify_loop, shape_execution_feedback  # noqa: E402


def test_classify_all_paths():
    assert (
        classify_loop(
            has_ledger=False, execution_outcome=None, has_outcome=False, outcome_success=None
        )
        == "execution_unknown"
    )
    assert (
        classify_loop(
            has_ledger=True, execution_outcome="failed", has_outcome=False, outcome_success=None
        )
        == "execution_failed"
    )
    assert (
        classify_loop(
            has_ledger=True, execution_outcome="executed", has_outcome=False, outcome_success=None
        )
        == "executed_unmeasured"
    )
    assert (
        classify_loop(
            has_ledger=True, execution_outcome="executed", has_outcome=True, outcome_success=None
        )
        == "executed_unmeasured"
    )
    assert (
        classify_loop(
            has_ledger=True, execution_outcome="executed", has_outcome=True, outcome_success=True
        )
        == "closed_ok"
    )
    assert (
        classify_loop(
            has_ledger=True, execution_outcome="executed", has_outcome=True, outcome_success=False
        )
        == "executed_off_plan"
    )


def test_no_ledger_is_unknown_not_assumed_executed():
    out = shape_execution_feedback([{"decision_id": "d1", "decision_type": "irrigation_plan"}])
    d = out["decisions"][0]
    assert d["loop_status"] == "execution_unknown"
    assert d["color"] == "gray"
    assert "لا يُفترَض تنفيذه" in d["note_ar"]
    assert out["totals"]["executed"] == 0


def test_executed_unmeasured_not_assumed_success():
    out = shape_execution_feedback(
        [{"decision_id": "d1", "execution_outcome": "executed", "has_outcome": False}]
    )
    d = out["decisions"][0]
    assert d["loop_status"] == "executed_unmeasured"
    assert d["outcome_measured"] is False
    assert "needs_data" in d["note_ar"]


def test_closed_ok_and_off_plan():
    out = shape_execution_feedback(
        [
            {
                "decision_id": "d1",
                "execution_outcome": "executed",
                "has_outcome": True,
                "outcome_success": True,
            },
            {
                "decision_id": "d2",
                "execution_outcome": "executed",
                "has_outcome": True,
                "outcome_success": False,
            },
        ]
    )
    statuses = {d["decision_id"]: d["loop_status"] for d in out["decisions"]}
    assert statuses["d1"] == "closed_ok"
    assert statuses["d2"] == "executed_off_plan"
    assert out["totals"]["closed_ok"] == 1
    assert out["totals"]["measured"] == 2


def test_failed_execution():
    out = shape_execution_feedback(
        [{"decision_id": "d1", "execution_outcome": "failed", "exec_note_ar": "انقطاع كهرباء"}]
    )
    d = out["decisions"][0]
    assert d["loop_status"] == "execution_failed"
    assert out["totals"]["failed"] == 1


def test_closure_rate_is_closed_over_executed():
    out = shape_execution_feedback(
        [
            {
                "decision_id": "d1",
                "execution_outcome": "executed",
                "has_outcome": True,
                "outcome_success": True,
            },
            {
                "decision_id": "d2",
                "execution_outcome": "executed",
                "has_outcome": True,
                "outcome_success": False,
            },
            {"decision_id": "d3", "execution_outcome": "executed", "has_outcome": False},
            {"decision_id": "d4", "execution_outcome": "failed"},
        ]
    )
    # المُنفَّذة = 3 (executed)؛ المغلقة بنجاح = 1 ⇒ 1/3.
    assert out["totals"]["executed"] == 3
    assert out["closure_rate"] == round(1 / 3, 3)


def test_empty_safe_closure_rate_none():
    out = shape_execution_feedback([], generated_at="2026-06-21T00:00:00+00:00")
    assert out["decision_count"] == 0
    assert out["closure_rate"] is None
    assert out["generated_at"] == "2026-06-21T00:00:00+00:00"
    assert out["provenance"]["calibrated"] == "not_applicable"
