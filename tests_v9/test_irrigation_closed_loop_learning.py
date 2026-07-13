from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "services" / "sahool-platform" / "api"
sys.path.insert(0, str(API))

from irrigation_closed_loop_learning import (  # noqa: E402
    REQUIRED_PRODUCTION_GATES,
    build_irrigation_closed_loop_record,
    build_irrigation_outcome_evidence,
    certify_irrigation_production_runtime,
    propose_governed_irrigation_learning,
)

D = "a" * 64


def _outcome(**overrides):
    args = {
        "tenant_id": "tenant-1",
        "field_id": "field-1",
        "season_id": "season-1",
        "decision_id": "decision-1",
        "execution_plan_id": "plan-1",
        "measured_at": "2026-07-13T12:00:00Z",
        "planned_depth_mm": 10.0,
        "actual_depth_mm": 9.5,
        "depletion_before_mm": 70.0,
        "depletion_after_mm": 60.0,
        "expected_depletion_after_mm": 60.5,
        "source_digests": {
            "decision_content_digest": D,
            "authorization_digest": D,
            "execution_plan_digest": D,
            "as_applied_digest": D,
            "water_ledger_event_digest": D,
        },
    }
    args.update(overrides)
    return build_irrigation_outcome_evidence(**args)


def _as_applied():
    return {
        "tenant_id": "tenant-1",
        "field_id": "field-1",
        "season_id": "season-1",
        "decision_id": "decision-1",
        "execution_plan_id": "plan-1",
        "status": "verified",
        "water_ledger_eligible": True,
        "as_applied_digest": D,
        "source_lineage": {"decision_content_digest": D},
    }


def _ledger():
    return {
        "tenant_id": "tenant-1",
        "field_id": "field-1",
        "season_id": "season-1",
        "decision_id": "decision-1",
        "execution_plan_id": "plan-1",
        "status": "persisted",
        "reconciled": True,
        "authorization_digest": D,
        "execution_plan_digest": D,
        "water_ledger_event_digest": D,
    }


def _closed(**overrides):
    args = {
        "tenant_id": "tenant-1",
        "field_id": "field-1",
        "season_id": "season-1",
        "decision_id": "decision-1",
        "authorization_id": "auth-1",
        "execution_plan_id": "plan-1",
        "decision_status": "approved",
        "approval_status": "approved",
        "execution_status": "completed",
        "as_applied_truth": _as_applied(),
        "water_ledger_event": _ledger(),
        "outcome_evidence": _outcome(),
    }
    args.update(overrides)
    return build_irrigation_closed_loop_record(**args)


def test_verified_closed_loop_has_complete_lineage():
    result = _closed()
    assert result.verified is True
    assert result.learning_eligible is True
    assert result.lifecycle_status == "verified"
    assert len(result.closed_loop_digest) == 64
    assert set(result.source_lineage) == {
        "decision_content_digest",
        "authorization_digest",
        "execution_plan_digest",
        "as_applied_digest",
        "water_ledger_event_digest",
        "outcome_evidence_digest",
    }


def test_missing_water_ledger_reconciliation_blocks_loop():
    ledger = _ledger()
    ledger["reconciled"] = False
    result = _closed(water_ledger_event=ledger)
    assert result.verified is False
    assert "RECONCILED_WATER_LEDGER_EVENT_REQUIRED" in result.blocking_reasons


def test_identity_mismatch_blocks_loop():
    applied = _as_applied()
    applied["field_id"] = "other-field"
    result = _closed(as_applied_truth=applied)
    assert result.verified is False
    assert "CLOSED_LOOP_FIELD_ID_MISMATCH" in result.blocking_reasons


def test_outcome_deviation_creates_human_review_proposal_only():
    outcome = _outcome(depletion_after_mm=78.0)
    closed = _closed(outcome_evidence=outcome)
    proposal = propose_governed_irrigation_learning(
        closed_loop=closed,
        outcome_evidence=outcome,
        minimum_samples=5,
        sample_count=8,
    )
    assert proposal.status == "review_ready"
    assert proposal.review_required is True
    assert proposal.auto_adjust is False
    assert proposal.proposed_parameter_changes


def test_insufficient_samples_block_learning_proposal():
    outcome = _outcome(depletion_after_mm=78.0)
    proposal = propose_governed_irrigation_learning(
        closed_loop=_closed(outcome_evidence=outcome),
        outcome_evidence=outcome,
        minimum_samples=5,
        sample_count=2,
    )
    assert proposal.status == "blocked"
    assert "MINIMUM_FIELD_SAMPLE_COUNT_NOT_MET" in proposal.limitations


def test_production_certification_blocks_missing_gate():
    gates = [
        {"gate": gate, "passed": True, "evidence_digest": D, "details": "ok"}
        for gate in REQUIRED_PRODUCTION_GATES
        if gate != "tenant_rls_isolation"
    ]
    result = certify_irrigation_production_runtime(
        environment="production",
        release_id="release-1",
        gate_results=gates,
        evidence_pack_digest=D,
        certified_by="reviewer-1",
        certified_at="2026-07-13T14:00:00Z",
    )
    assert result.production_certified is False
    assert "tenant_rls_isolation" in result.blocking_gates


def test_production_certification_requires_evidence_digest_per_gate():
    gates = [
        {"gate": gate, "passed": True, "evidence_digest": D, "details": "ok"}
        for gate in REQUIRED_PRODUCTION_GATES
    ]
    gates[0]["evidence_digest"] = "bad"
    result = certify_irrigation_production_runtime(
        environment="production",
        release_id="release-1",
        gate_results=gates,
        evidence_pack_digest=D,
        certified_by="reviewer-1",
        certified_at="2026-07-13T14:00:00Z",
    )
    assert result.production_certified is False


def test_all_production_gates_can_issue_certification():
    gates = [
        {"gate": gate, "passed": True, "evidence_digest": D, "details": "verified"}
        for gate in REQUIRED_PRODUCTION_GATES
    ]
    result = certify_irrigation_production_runtime(
        environment="production",
        release_id="release-1",
        gate_results=gates,
        evidence_pack_digest=D,
        certified_by="independent-reviewer",
        certified_at="2026-07-13T14:00:00Z",
    )
    assert result.production_certified is True
    assert result.status == "certified"
    assert result.blocking_gates == []
    assert len(result.certification_digest) == 64


pytestmark = pytest.mark.unit
