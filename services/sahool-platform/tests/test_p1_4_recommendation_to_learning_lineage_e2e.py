"""P1.4 E2E lineage guard for recommendation → decision → outcome → learning read paths.

This is deliberately a pure, in-process E2E contract: it wires the same deterministic core/read-path
functions used by the runtime without requiring Postgres, NATS, or HTTP. The purpose is to prevent the
loop from becoming paper-only again: a recommendation outcome must be linkable to a decision, counted
only when decided, and usable as a traceable learning source.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from api.field_season_projection import assemble_field_season_state
from api.learning_summary import summarize_learning_with_reconciled_outcomes
from core.learning_source_lineage import resolve_learning_source
from core.loop_referential_integrity import reconciliation_report
from core.outcome_reconciler import reconcile_outcomes


def _ts(day: int) -> datetime:
    return datetime(2026, 7, day, 12, 0, tzinfo=UTC)


def test_recommendation_decision_outcome_learning_lineage_reaches_both_read_paths():
    """A complete loop is clean, linked, traceable, and visible in learning + season state."""
    recommendation_rows = [{"recommendation_id": "rec_1", "field_id": "fld_1"}]
    decision_rows = [{"decision_id": "dec_1", "region": "jawf", "created_at": _ts(1)}]
    dispatch_rows = [{"id": "dispatch_1", "recommendation_id": "rec_1", "decision_id": "dec_1"}]
    outcome_records = [
        {
            "outcome_id": "or_1",
            "field_id": "fld_1",
            "region": "jawf",
            "decision_id": "dec_1",
            "success": True,
            "metrics": {"n_evaluated": 1, "n_success": 1},
            "created_at": _ts(3),
        }
    ]
    recommendation_outcomes = [
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
            "issued_at": _ts(2),
            "outcome_recorded_at": _ts(4),
        }
    ]
    dispatch_links = {row["recommendation_id"]: row["decision_id"] for row in dispatch_rows}

    integrity = reconciliation_report(
        outcome_rows=outcome_records,
        known_decision_ids={row["decision_id"] for row in decision_rows},
        dispatch_rows=dispatch_rows,
        known_recommendation_ids={row["recommendation_id"] for row in recommendation_rows},
    )
    assert integrity["clean"] is True
    assert integrity["orphan_outcome_count"] == 0
    assert integrity["orphan_dispatch_count"] == 0

    reconciled = reconcile_outcomes(
        outcome_records,
        recommendation_outcomes,
        dispatch_links=dispatch_links,
    )
    assert reconciled["total"] == 2
    assert reconciled["by_source"] == {"outcome_record": 1, "recommendation_outcomes": 1}
    assert len(reconciled["linked_groups"]) == 1
    linked_members = reconciled["linked_groups"][0]["members"]
    assert {member["source_model"] for member in linked_members} == {
        "outcome_record",
        "recommendation_outcomes",
    }

    learning_source = resolve_learning_source(
        {
            "source_type": "recommendation_outcome",
            "source_id": "ro_1",
            "field_id": "fld_1",
            "season_id": "ssn_1",
            "recommendation_id": "rec_1",
            "decision_id": "dec_1",
        }
    )
    assert learning_source["traceability_status"] == "traceable"
    assert learning_source["applies"] is True

    learning_summary = summarize_learning_with_reconciled_outcomes(
        decision_rows=decision_rows,
        outcome_records=outcome_records,
        recommendation_outcomes=recommendation_outcomes,
        dispatch_links=dispatch_links,
    )
    assert learning_summary["overall"]["outcome_count"] == 2
    assert learning_summary["overall"]["outcomes_decided"] == 2
    assert learning_summary["overall"]["sample_count"] == 2
    assert learning_summary["overall"]["success_rate"] == 1.0
    assert learning_summary["outcome_reconciliation"]["linked_group_count"] == 1

    season_state = assemble_field_season_state(
        field_id="fld_1",
        season_id="ssn_1",
        crop="wheat",
        sowing_date=date(2025, 11, 1),
        today=date(2025, 12, 21),
        observed_ndvi=0.56,
        weather_signals={"tmax_c": 24},
        water_deficit_7d_mm=5.0,
        outcome_records=outcome_records,
        recommendation_outcomes=recommendation_outcomes,
        dispatch_links=dispatch_links,
    )
    assert season_state["outcome_reconciliation"]["total"] == 2
    assert season_state["outcome_reconciliation"]["sample_count"] == 2
    assert season_state["outcome_reconciliation"]["linked_group_count"] == 1
    assert "outcomes" in season_state["evidence_used"]


def test_pending_or_untraceable_loop_does_not_apply_or_inflate_evidence():
    """Missing maturity/source is visible but never promoted to trusted learning evidence."""
    recommendation_outcomes = [
        {
            "outcome_id": "ro_pending",
            "field_id": "fld_1",
            "region": "jawf",
            "season_id": "ssn_1",
            "crop": "wheat",
            "recommendation_id": "rec_pending",
            "predicted_yield_t_ha": 4.0,
            "actual_yield_t_ha": None,
            "accepted": True,
            "matured_within_lag": False,
            "issued_at": _ts(2),
        }
    ]

    untraceable = resolve_learning_source(
        {
            "source_type": "recommendation_outcome",
            "source_id": "",
            "field_id": "fld_1",
            "season_id": "ssn_1",
            "recommendation_id": "rec_pending",
        }
    )
    assert untraceable["traceability_status"] == "pending_review"
    assert untraceable["applies"] is False

    learning_summary = summarize_learning_with_reconciled_outcomes(
        decision_rows=[],
        outcome_records=[],
        recommendation_outcomes=recommendation_outcomes,
    )
    assert learning_summary["overall"]["outcome_count"] == 1
    assert learning_summary["overall"]["outcomes_pending"] == 1
    assert learning_summary["overall"]["sample_count"] == 0
    assert learning_summary["overall"]["success_rate"] is None

    season_state = assemble_field_season_state(
        field_id="fld_1",
        season_id="ssn_1",
        crop="wheat",
        sowing_date=date(2025, 11, 1),
        today=date(2025, 12, 21),
        recommendation_outcomes=recommendation_outcomes,
    )
    assert season_state["outcome_reconciliation"]["total"] == 1
    assert season_state["outcome_reconciliation"]["pending"] == 1
    assert season_state["outcome_reconciliation"]["sample_count"] == 0
    assert season_state["outcome_reconciliation"]["success_rate"] is None
