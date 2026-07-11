"""WX-10.7 SoR-promotion cutover-prep — pure review-backfill classifier (unit).

Exercises `backfill.classify_candidates` with injected rows (no DB) so the quarantine/parity logic
is deterministic and cannot rot. The contract: a candidate that migration 002 could not backfill
into an authoritatively reviewable row is QUARANTINED (surfaced, never guessed, never mutated); a
NULL candidate_lineage_id is fail-closed un-reviewable, not a silent mis-approval.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_BACKFILL = Path(__file__).resolve().parents[1] / "services" / "decision-service" / "backfill.py"
_spec = importlib.util.spec_from_file_location("decision_backfill_under_test", _BACKFILL)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
classify_candidates = _mod.classify_candidates


def _row(decision_id, review_state, lineage, evidence_status="pending_approval", stage="candidate"):
    return {
        "decision_id": decision_id,
        "stage": stage,
        "review_state": review_state,
        "candidate_lineage_id": lineage,
        "evidence_status": evidence_status,
    }


def test_clean_candidates_pass_no_quarantine():
    rows = [
        _row("d1", "pending_approval", "lin-1"),
        _row("d2", "approved", "lin-2"),
        _row("d3", "rejected", "lin-3"),
    ]
    quarantine, parity, ok = classify_candidates(rows)
    assert ok is True
    assert quarantine == []
    assert parity["candidates"] == 3
    assert parity["pending_approval"] == 1
    assert parity["approved"] == 1
    assert parity["rejected"] == 1


def test_null_lineage_is_quarantined_fail_closed():
    quarantine, parity, ok = classify_candidates([_row("d1", "pending_approval", None)])
    assert ok is False
    assert parity["missing_lineage"] == 1
    assert len(quarantine) == 1
    assert quarantine[0]["decision_id"] == "d1"
    assert any("un-reviewable" in r for r in quarantine[0]["reasons"])


def test_empty_string_lineage_is_quarantined():
    quarantine, _parity, ok = classify_candidates([_row("d1", "pending_approval", "   ")])
    assert ok is False
    assert len(quarantine) == 1


def test_unbackfilled_review_state_null_is_quarantined():
    quarantine, parity, ok = classify_candidates([_row("d1", None, "lin-1")])
    assert ok is False
    assert parity["review_state_null"] == 1
    assert any("not backfilled" in r for r in quarantine[0]["reasons"])


def test_invalid_review_state_is_quarantined():
    quarantine, parity, ok = classify_candidates([_row("d1", "bogus", "lin-1")])
    assert ok is False
    assert parity["invalid_review_state"] == 1
    assert any("invalid review_state" in r for r in quarantine[0]["reasons"])


def test_evidence_status_mismatch_is_ambiguous_quarantine():
    quarantine, parity, ok = classify_candidates(
        [_row("d1", "pending_approval", "lin-1", evidence_status="draft")]
    )
    assert ok is False
    assert parity["evidence_status_mismatch"] == 1
    assert any("disagrees" in r for r in quarantine[0]["reasons"])


def test_evidence_status_absent_is_tolerated():
    # A candidate whose evidence jsonb lacks a 'status' key (None) is not flagged for that reason.
    quarantine, _parity, ok = classify_candidates(
        [_row("d1", "pending_approval", "lin-1", evidence_status=None)]
    )
    assert ok is True
    assert quarantine == []


def test_non_candidate_rows_ignored():
    rows = [_row("d1", None, None, stage="final"), _row("d2", "pending_approval", "lin-2")]
    quarantine, parity, ok = classify_candidates(rows)
    assert ok is True
    assert parity["candidates"] == 1
    assert quarantine == []
