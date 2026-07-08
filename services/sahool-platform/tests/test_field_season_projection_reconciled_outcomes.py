"""Tests for wiring reconciled outcomes into the field-season operational truth."""

from __future__ import annotations

from datetime import UTC, date, datetime

from api.field_season_projection import assemble_field_season_state


def _ts(day: int) -> datetime:
    return datetime(2026, 7, day, 12, 0, tzinfo=UTC)


def test_field_season_state_exposes_reconciled_outcome_sources_and_success_rate():
    state = assemble_field_season_state(
        field_id="fld_1",
        season_id="ssn_1",
        crop="wheat",
        sowing_date=date(2025, 11, 1),
        today=date(2025, 12, 21),
        observed_ndvi=0.55,
        weather_signals={"tmax_c": 25},
        outcome_records=[
            {
                "outcome_id": "or_1",
                "field_id": "fld_1",
                "region": "jawf",
                "decision_id": "dec_1",
                "success": True,
                "created_at": _ts(2),
            }
        ],
        recommendation_outcomes=[
            {
                "outcome_id": "ro_1",
                "field_id": "fld_1",
                "region": "jawf",
                "season_id": "ssn_1",
                "recommendation_id": "rec_1",
                "predicted_yield_t_ha": 4.0,
                "actual_yield_t_ha": 4.5,
                "accepted": True,
                "matured_within_lag": True,
                "outcome_recorded_at": _ts(3),
            }
        ],
        dispatch_links={"rec_1": "dec_1"},
    )

    rec = state["outcome_reconciliation"]
    assert rec["enabled"] is True
    assert rec["total"] == 2
    assert rec["decided"] == 2
    assert rec["pending"] == 0
    assert rec["success_rate"] == 1.0
    assert rec["sample_count"] == 2
    assert rec["by_source"] == {"outcome_record": 1, "recommendation_outcomes": 1}
    assert rec["by_kind"] == {"decision_effect": 1, "yield_learning": 1}
    assert rec["linked_group_count"] == 1
    assert "outcomes" in state["evidence_used"]


def test_pending_recommendation_outcome_does_not_raise_samples_or_success_rate():
    state = assemble_field_season_state(
        field_id="fld_1",
        season_id="ssn_1",
        crop="wheat",
        sowing_date=date(2025, 11, 1),
        today=date(2025, 12, 21),
        recommendation_outcomes=[
            {
                "outcome_id": "ro_pending",
                "field_id": "fld_1",
                "region": "jawf",
                "season_id": "ssn_1",
                "recommendation_id": "rec_pending",
                "predicted_yield_t_ha": 4.0,
                "actual_yield_t_ha": None,
                "accepted": True,
                "matured_within_lag": False,
                "issued_at": _ts(1),
            }
        ],
    )

    rec = state["outcome_reconciliation"]
    assert rec["total"] == 1
    assert rec["decided"] == 0
    assert rec["pending"] == 1
    assert rec["success_rate"] is None
    assert rec["sample_count"] == 0
    assert "outcomes" in state["evidence_used"]


def test_empty_outcomes_are_explicitly_missing_not_fabricated():
    state = assemble_field_season_state(crop="wheat", sowing_date=date(2025, 11, 1))
    rec = state["outcome_reconciliation"]
    assert rec["enabled"] is True
    assert rec["total"] == 0
    assert rec["success_rate"] is None
    assert rec["sample_count"] == 0
    assert "outcomes" in state["evidence_missing"]
