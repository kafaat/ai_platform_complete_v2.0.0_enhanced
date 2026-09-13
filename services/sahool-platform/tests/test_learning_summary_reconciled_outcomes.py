"""Tests for the reconciled outcome read path used by the learning dashboard."""

from __future__ import annotations

from datetime import UTC, datetime

from api.learning_summary import summarize_learning_with_reconciled_outcomes


def _ts(day: int) -> datetime:
    return datetime(2026, 7, day, 12, 0, tzinfo=UTC)


def test_learning_summary_counts_both_outcome_models_with_source_metadata():
    out = summarize_learning_with_reconciled_outcomes(
        decision_rows=[{"region": "jawf", "created_at": _ts(1)}],
        outcome_records=[
            {
                "outcome_id": "or_1",
                "field_id": "fld_1",
                "region": "jawf",
                "decision_id": "dec_1",
                "success": True,
                "metrics": {"n_evaluated": 3, "n_success": 3},
                "created_at": _ts(2),
            }
        ],
        recommendation_outcomes=[
            {
                "outcome_id": "ro_1",
                "field_id": "fld_1",
                "region": "jawf",
                "season_id": "ssn_1",
                "crop": "wheat",
                "recommendation_id": "rec_1",
                "predicted_yield_t_ha": 4.0,
                "actual_yield_t_ha": 4.4,
                "accepted": True,
                "matured_within_lag": True,
                "outcome_recorded_at": _ts(3),
            }
        ],
        dispatch_links={"rec_1": "dec_1"},
    )

    assert out["overall"]["outcome_count"] == 2
    assert out["overall"]["outcomes_succeeded"] == 2
    assert out["overall"]["success_rate"] == 1.0
    assert out["outcome_reconciliation"]["by_source"] == {
        "outcome_record": 1,
        "recommendation_outcomes": 1,
    }
    assert out["outcome_reconciliation"]["by_kind"] == {
        "decision_effect": 1,
        "yield_learning": 1,
    }
    assert out["outcome_reconciliation"]["linked_group_count"] == 1


def test_unmatured_recommendation_outcome_stays_pending_and_does_not_inflate_evidence():
    out = summarize_learning_with_reconciled_outcomes(
        decision_rows=[],
        outcome_records=[],
        recommendation_outcomes=[
            {
                "outcome_id": "ro_pending",
                "field_id": "fld_1",
                "region": "jawf",
                "recommendation_id": "rec_pending",
                "predicted_yield_t_ha": 4.0,
                "actual_yield_t_ha": None,
                "accepted": True,
                "matured_within_lag": False,
                "issued_at": _ts(1),
            }
        ],
    )

    assert out["overall"]["outcome_count"] == 1
    assert out["overall"]["outcomes_pending"] == 1
    assert out["overall"]["outcomes_decided"] == 0
    assert out["overall"]["success_rate"] is None
    assert out["overall"]["sample_count"] == 0


def test_immature_outcome_with_an_early_actual_value_stays_pending():
    """U02 (التدقيق الموحَّد 2026-09-13): قيمة فعليّة مبكّرة قبل النضج كانت تدخل النجاح."""
    out = summarize_learning_with_reconciled_outcomes(
        decision_rows=[],
        outcome_records=[],
        recommendation_outcomes=[
            {
                "outcome_id": "ro_early",
                "field_id": "fld_1",
                "region": "jawf",
                "recommendation_id": "rec_early",
                "predicted_yield_t_ha": 4.0,
                "actual_yield_t_ha": 4.4,
                "accepted": True,
                "matured_within_lag": False,
                "issued_at": _ts(1),
            }
        ],
    )
    assert out["overall"]["outcomes_pending"] == 1
    assert out["overall"]["outcomes_decided"] == 0
    assert out["overall"]["success_rate"] is None
    assert out["overall"]["sample_count"] == 0


def test_eligibility_reasons_are_explicit_and_non_finite_values_are_rejected():
    from core.outcome_reconciler import (
        normalize_recommendation_outcome,
        recommendation_outcome_eligibility,
    )

    base = {"predicted_yield_t_ha": 4.0, "actual_yield_t_ha": 4.4, "accepted": True}
    assert recommendation_outcome_eligibility({**base, "matured_within_lag": True}) == {
        "eligible": True,
        "reason": None,
    }
    assert recommendation_outcome_eligibility({**base, "matured_within_lag": False})["reason"] == (
        "immature"
    )
    assert (
        recommendation_outcome_eligibility({**base, "matured_within_lag": True, "accepted": False})[
            "reason"
        ]
        == "not_accepted"
    )
    # دراسة دقّة التوقّع لا تشترط القبول.
    assert recommendation_outcome_eligibility(
        {**base, "matured_within_lag": True, "accepted": False}, require_acceptance=False
    )["eligible"]
    assert (
        recommendation_outcome_eligibility(
            {**base, "matured_within_lag": True, "actual_yield_t_ha": "nan"}
        )["reason"]
        == "non_finite_value"
    )
    assert recommendation_outcome_eligibility({**base, "actual_yield_t_ha": None})["reason"] == (
        "missing_actual"
    )
    row = normalize_recommendation_outcome({**base, "matured_within_lag": False})
    assert row["success"] is None
    assert row["result"]["eligibility"]["reason"] == "immature"


def test_one_linked_case_counts_as_one_independent_case_not_two_samples():
    """U03: صفّان مربوطان بالقرار نفسه = حالة واحدة؛ الصفوف تُعدّ صفوفاً باسمها."""
    out = summarize_learning_with_reconciled_outcomes(
        decision_rows=[],
        outcome_records=[
            {
                "outcome_id": "or_1",
                "field_id": "fld_1",
                "region": "jawf",
                "decision_id": "dec_1",
                "success": True,
                "metrics": {"n_evaluated": 1, "n_success": 1},
                "created_at": _ts(2),
            }
        ],
        recommendation_outcomes=[
            {
                "outcome_id": "ro_1",
                "field_id": "fld_1",
                "region": "jawf",
                "recommendation_id": "rec_1",
                "predicted_yield_t_ha": 4.0,
                "actual_yield_t_ha": 4.4,
                "accepted": True,
                "matured_within_lag": True,
                "outcome_recorded_at": _ts(3),
            },
            {
                "outcome_id": "ro_2",
                "field_id": "fld_2",
                "region": "jawf",
                "recommendation_id": "rec_2",
                "predicted_yield_t_ha": 3.0,
                "actual_yield_t_ha": 3.1,
                "accepted": True,
                "matured_within_lag": True,
                "outcome_recorded_at": _ts(4),
            },
        ],
        dispatch_links={"rec_1": "dec_1"},
    )
    rec = out["outcome_reconciliation"]
    assert rec["linked_group_count"] == 1
    assert rec["rows_by_source"] == {"outcome_record": 1, "recommendation_outcomes": 2}
    assert rec["sample_count_basis"] == "rows"
    assert rec["independent_case_count"] == 2  # (or_1+ro_1) حالة واحدة + ro_2
    assert out["overall"]["sample_count"] == 3  # الصفوف كما هي — مُسمّاة لا مُخفاة
