"""PEST-EXECUTION-RESULT-TRUTH-01: workflow completion is not physical execution.

The API exposes a *separate*, tri-state agricultural execution projection.  A
completed saga may never have sprayed; a failed/compensated saga may have sprayed
and cannot safely be called "not executed" without reconciliation.
"""

import pytest
from core.pest_escalation_flow import summarize_pest_execution
from core.workflow_engine import WorkflowState, WorkflowStatus

pytestmark = pytest.mark.unit


def _state(status, execute=None):
    return WorkflowState(
        workflow_id="pest-receipt-1",
        status=status,
        step_results={} if execute is None else {"execute": execute},
    )


def test_suspended_before_execute_is_not_attempted():
    result = summarize_pest_execution(_state(WorkflowStatus.SUSPENDED))
    assert result == {
        "status": "not_attempted",
        "executed": False,
        "execution_ref": None,
        "reason": "execution_step_not_reached",
    }


def test_completed_workflow_without_executor_did_not_spray():
    result = summarize_pest_execution(
        _state(
            WorkflowStatus.COMPLETED,
            {
                "executed": False,
                "execution_ref": None,
                "reason": "executor_not_configured",
            },
        )
    )
    assert result == {
        "status": "not_executed",
        "executed": False,
        "execution_ref": None,
        "reason": "executor_not_configured",
    }


def test_only_literal_true_with_nonblank_reference_confirms_execution():
    confirmed = summarize_pest_execution(
        _state(WorkflowStatus.COMPLETED, {"executed": True, "execution_ref": "spray-job-7"})
    )
    assert confirmed == {
        "status": "executed",
        "executed": True,
        "execution_ref": "spray-job-7",
        "reason": None,
    }


@pytest.mark.parametrize("value", [1, "true", None, {}, False])
def test_truthy_or_missing_ack_with_reference_requires_reconciliation(value):
    raw = {"executed": value, "execution_ref": "spray-job-7"}
    result = summarize_pest_execution(_state(WorkflowStatus.COMPLETED, raw))
    assert result["status"] == "reconciliation_required", result
    assert result["executed"] is None, result
    assert result["execution_ref"] == "spray-job-7", result


@pytest.mark.parametrize("ref", [None, "", "   ", 99])
def test_executor_ack_without_valid_reference_requires_reconciliation(ref):
    result = summarize_pest_execution(
        _state(WorkflowStatus.COMPLETED, {"executed": True, "execution_ref": ref})
    )
    assert result["status"] == "reconciliation_required", result
    assert result["executed"] is None, result
    assert result["execution_ref"] is None, result


@pytest.mark.parametrize(
    "status",
    [
        WorkflowStatus.FAILED,
        WorkflowStatus.COMPENSATED,
        WorkflowStatus.COMPENSATION_FAILED,
    ],
)
def test_proven_prior_execution_with_noncompleted_saga_needs_reconciliation(status):
    result = summarize_pest_execution(
        _state(status, {"executed": True, "execution_ref": "spray-job-7"})
    )
    assert result["status"] == "reconciliation_required", result
    assert result["executed"] is None, result
    assert result["execution_ref"] == "spray-job-7", result


def test_failed_compensation_cannot_claim_no_physical_side_effect():
    result = summarize_pest_execution(
        _state(WorkflowStatus.COMPENSATION_FAILED, {"executed": False})
    )
    assert result["status"] == "reconciliation_required", result
    assert result["executed"] is None, result


def test_guardrails_denial_without_executor_is_not_executed():
    result = summarize_pest_execution(
        _state(
            WorkflowStatus.COMPLETED,
            {"executed": False, "blocked_by": "guardrails"},
        )
    )
    assert result["status"] == "not_executed", result
    assert result["executed"] is False, result
    assert result["reason"] == "guardrails", result


@pytest.mark.parametrize(
    "execute",
    [
        {},
        {"executed": "true"},
        {"executed": 1},
        {"executed": False, "reason": "execution_not_confirmed"},
        {"executed": False, "reason": "execution_ref_missing"},
    ],
)
def test_unconfirmed_worker_result_without_ref_is_not_proof_of_no_spray(execute):
    result = summarize_pest_execution(_state(WorkflowStatus.COMPLETED, execute))
    assert result["status"] == "reconciliation_required", result
    assert result["executed"] is None, result


@pytest.mark.parametrize(
    "status",
    [WorkflowStatus.RUNNING, WorkflowStatus.FAILED, WorkflowStatus.COMPENSATED],
)
def test_execute_started_but_crashed_before_ack_is_uncertain(status):
    state = _state(status)
    state.current_step = "execute"
    result = summarize_pest_execution(state)
    assert result["status"] == "reconciliation_required", result
    assert result["executed"] is None, result
    assert result["reason"] == "execution_outcome_unknown", result


def test_failure_before_reaching_execution_is_not_attempted():
    state = _state(WorkflowStatus.FAILED)
    state.current_step = "detect"
    result = summarize_pest_execution(state)
    assert result["status"] == "not_attempted", result
    assert result["executed"] is False, result


def test_inconsistent_completed_without_execution_step_requires_reconciliation():
    result = summarize_pest_execution(_state(WorkflowStatus.COMPLETED))
    assert result["status"] == "reconciliation_required", result
    assert result["executed"] is None, result

