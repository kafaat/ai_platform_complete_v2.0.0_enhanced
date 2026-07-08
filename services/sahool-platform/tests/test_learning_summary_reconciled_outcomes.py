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
