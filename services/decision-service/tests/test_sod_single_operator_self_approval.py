"""Single-operator self-approval exception to separation of duties (no database).

Owner decision on DECISION-SOD-SINGLE-USER-FARM-POLICY-01: a single-user farm may explicitly
self-approve a LOW-risk candidate under an audited, tenant-scoped exception; HIGH-risk,
physical-effect, financial and sensitive decisions still need an independent approver. Default
OFF. Pure functions plus the HTTP edge with persistence mocked.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-00000000a5a5"
OTHER = "00000000-0000-0000-0000-00000000b6b6"
TOKEN = "isolated-test-token"
POLICY_ENV = (
    "DECISION_SOD_SELF_APPROVAL_TENANTS",
    "DECISION_SOD_SELF_APPROVAL_DECISION_TYPES",
    "DECISION_SOD_SELF_APPROVAL_MAX_RISK",
)


@pytest.fixture(autouse=True)
def _clean_policy_env(monkeypatch):
    for name in POLICY_ENV:
        monkeypatch.delenv(name, raising=False)


def _enable(monkeypatch, *, tenants=TENANT, types="crop_decision_candidate", max_risk=None):
    monkeypatch.setenv("DECISION_SOD_SELF_APPROVAL_TENANTS", tenants)
    monkeypatch.setenv("DECISION_SOD_SELF_APPROVAL_DECISION_TYPES", types)
    if max_risk is not None:
        monkeypatch.setenv("DECISION_SOD_SELF_APPROVAL_MAX_RISK", max_risk)


def _verdict(**over):
    from persistence import evaluate_self_approval

    args = dict(
        tenant_id=TENANT,
        action="approve",
        decision_type="crop_decision_candidate",
        decision_value={"risk_level": "LOW", "candidate_lineage_id": "cand/1"},
        proposer="u-solo",
        approver="u-solo",
        acknowledged=True,
        acknowledgement_reason="single-operator farm",
    )
    args.update(over)
    return evaluate_self_approval(**args)


# ── default OFF ───────────────────────────────────────────────────────────────────────────
def test_the_exception_is_disabled_by_default():
    from persistence import self_approval_policy

    assert self_approval_policy() == {"enabled": False, "reason": "not_configured"}
    verdict = _verdict()
    assert verdict["allowed"] is False
    assert verdict["refusal"] == "self_approval_not_enabled_for_tenant"


# ── the one allowed shape ─────────────────────────────────────────────────────────────────
def test_enabled_tenant_low_risk_allowlisted_and_acknowledged_is_allowed_and_audited(
    monkeypatch,
):
    _enable(monkeypatch)
    verdict = _verdict(approver=" u-solo ")
    assert verdict["allowed"] is True
    assert verdict["audit"] == {
        "policy_id": "decision-sod-single-operator-exception",
        "policy_version": "1",
        "tenant_id": TENANT,
        "decision_type": "crop_decision_candidate",
        "risk_level": "LOW",
        "max_risk_level": "LOW",
        "proposer": "u-solo",
        "approver": "u-solo",
        "acknowledged": True,
        "reason": "single-operator farm",
    }


# ── every missing condition still refuses ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    "over, refusal",
    [
        ({"tenant_id": OTHER}, "self_approval_not_enabled_for_tenant"),
        ({"tenant_id": "not-a-uuid"}, "self_approval_not_enabled_for_tenant"),
        ({"action": "reject"}, "self_approval_covers_approval_only"),
        (
            {"decision_type": "remote_sensing_diagnosis_referral"},
            "self_approval_operation_not_allowlisted",
        ),
        ({"decision_value": {"risk_level": "MEDIUM"}}, "self_approval_risk_above_bound"),
        ({"decision_value": {}}, "self_approval_risk_above_bound"),
        ({"decision_value": {"risk_level": "negligible"}}, "self_approval_risk_above_bound"),
        ({"acknowledged": False}, "self_approval_acknowledgement_required"),
        ({"acknowledgement_reason": "   "}, "self_approval_acknowledgement_required"),
        ({"acknowledgement_reason": None}, "self_approval_acknowledgement_required"),
    ],
)
def test_each_missing_condition_is_refused_with_its_code(monkeypatch, over, refusal):
    _enable(monkeypatch)
    verdict = _verdict(**over)
    assert verdict["allowed"] is False
    assert verdict["refusal"] == refusal
    assert verdict["message"].startswith(f"separation_of_duties_violation ({refusal})")
    assert "independent approver" in verdict["message"]


def test_an_undeclared_risk_counts_as_critical():
    from persistence import candidate_risk_level

    assert candidate_risk_level({}) == "CRITICAL"
    assert candidate_risk_level(None) == "CRITICAL"
    assert candidate_risk_level({"risk_level": " low "}) == "LOW"
    assert candidate_risk_level({"risk_level": "LOW", "requires_expert_review": True}) == "HIGH"


def test_medium_bound_admits_medium_but_never_high(monkeypatch):
    _enable(monkeypatch, max_risk="medium")
    assert _verdict(decision_value={"risk_level": "MEDIUM"})["allowed"] is True
    for value in ({"risk_level": "HIGH"}, {"risk_level": "CRITICAL"}):
        verdict = _verdict(decision_value=value)
        assert verdict["refusal"] == "self_approval_risk_above_bound"
    expert = _verdict(decision_value={"risk_level": "LOW", "requires_expert_review": True})
    assert expert["refusal"] == "self_approval_risk_above_bound"


# ── hard exclusions regardless of config ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    "decision_type",
    [
        "irrigation",
        "irrigation_deficit",
        "irrigation_mpc",
        "irrigation_plan",
        "weather_operation_plan",
        "fertigation_schedule",
        "payment_release",
        "input_purchase",
        "model_activation",
        "tenant_access_grant",
    ],
)
def test_physical_financial_and_sensitive_types_are_always_refused(monkeypatch, decision_type):
    from persistence import decision_type_hard_excluded

    assert decision_type_hard_excluded(decision_type)
    _enable(monkeypatch)
    verdict = _verdict(decision_type=decision_type)
    assert verdict["refusal"] == "self_approval_excluded_operation"
    assert "independent approver" in verdict["message"]


@pytest.mark.parametrize("key", ["manual_execution_source", "command", "command_payload"])
def test_a_candidate_carrying_a_physical_effect_specification_is_refused(monkeypatch, key):
    _enable(monkeypatch)
    verdict = _verdict(decision_value={"risk_level": "LOW", key: {"x": 1}})
    assert verdict["refusal"] == "self_approval_excluded_operation"


@pytest.mark.parametrize(
    "decision_type", ["crop_decision_candidate", "recommendation", "crop_twin"]
)
def test_advisory_types_are_not_hard_excluded(decision_type):
    from persistence import decision_type_hard_excluded

    assert not decision_type_hard_excluded(decision_type)


def test_other_tenants_keep_strict_separation_of_duties(monkeypatch):
    _enable(monkeypatch, tenants=f"{TENANT}, {TENANT.upper()}")
    assert _verdict()["allowed"] is True
    assert _verdict(tenant_id=OTHER)["refusal"] == "self_approval_not_enabled_for_tenant"


# ── malformed configuration disables the exception (strict SoD applies) ───────────────────
@pytest.mark.parametrize(
    "tenants, types, max_risk",
    [
        ("*", "crop_decision_candidate", None),
        (f"{TENANT},not-a-uuid", "crop_decision_candidate", None),
        (TENANT, "", None),
        (TENANT, "crop_decision_candidate,Bad Type", None),
        (TENANT, "crop_decision_candidate,irrigation", None),
        (TENANT, "crop_decision_candidate", "HIGH"),
        (TENANT, "crop_decision_candidate", "CRITICAL"),
        (TENANT, "crop_decision_candidate", "low-ish"),
    ],
)
def test_malformed_configuration_disables_the_exception_and_is_logged(
    monkeypatch, caplog, tenants, types, max_risk
):
    from persistence import self_approval_policy

    _enable(monkeypatch, tenants=tenants, types=types, max_risk=max_risk)
    with caplog.at_level(logging.ERROR, logger="persistence"):
        policy = _fresh_policy()
    assert policy["enabled"] is False and policy["reason"] == "invalid"
    assert any("self-approval exception DISABLED" in r.getMessage() for r in caplog.records)
    verdict = _verdict()
    assert verdict["allowed"] is False
    assert verdict["refusal"] == "self_approval_policy_invalid"
    assert self_approval_policy()["enabled"] is False


def _fresh_policy():
    import persistence

    persistence.parse_self_approval_policy.cache_clear()
    return persistence.self_approval_policy()


# ── the audit marker is bound to the review's request hash ────────────────────────────────
def test_the_audit_marker_round_trips_and_is_part_of_the_request_hash(monkeypatch):
    from persistence import (
        SELF_APPROVAL_REASON_PREFIX,
        _request_hash,
        self_approval_audit_from_reason,
        self_approval_review_reason,
    )

    _enable(monkeypatch)
    audit = _verdict()["audit"]
    stored = self_approval_review_reason(audit, "looks fine")
    assert stored.startswith(SELF_APPROVAL_REASON_PREFIX)
    assert self_approval_audit_from_reason(stored) == audit
    assert self_approval_audit_from_reason("looks fine") is None
    assert self_approval_audit_from_reason(SELF_APPROVAL_REASON_PREFIX + "{broken") is None

    semantic = dict(
        decision_id="d",
        action="approve",
        new_state="approved",
        candidate_lineage_id="lin",
        decision_value_digest="a" * 64,
        policy_version="rev/1",
    )
    with_marker = _request_hash(**semantic, reason=stored)
    assert with_marker != _request_hash(**semantic, reason="looks fine"), "strip is detectable"
    tampered = self_approval_review_reason({**audit, "risk_level": "HIGH"}, "looks fine")
    assert with_marker != _request_hash(**semantic, reason=tampered)


def test_the_authoritative_review_reports_the_saved_marker(monkeypatch):
    from persistence import _reviewed, self_approval_review_reason

    _enable(monkeypatch)
    audit = _verdict()["audit"]
    row = {
        "reviewed_at": "2026-11-09T00:00:00+00:00",
        "decision_id": "d",
        "previous_state": "pending_approval",
        "new_state": "approved",
        "review_id": "rev_1",
        "reviewed_by": "u-solo",
        "candidate_lineage_id": "lin",
        "approved_decision_value_digest": "a" * 64,
        "reason": self_approval_review_reason(audit, ""),
    }
    assert _reviewed(row, replay=False)["self_approval"] == audit
    assert _reviewed({**row, "reason": "ok"}, replay=False)["self_approval"] is None


@pytest.mark.asyncio
async def test_persistence_refuses_a_forged_marker_before_any_io(monkeypatch):
    import persistence

    monkeypatch.setattr(
        persistence, "_connect", AsyncMock(side_effect=AssertionError("no database"))
    )
    result = await persistence.review_decision(
        tenant_id=TENANT,
        decision_id="d",
        action="approve",
        new_state="approved",
        reason=persistence.SELF_APPROVAL_REASON_PREFIX + "{}",
        reviewed_by="u",
        candidate_lineage_id="lin",
        idempotency_key="k",
        policy_version="rev/1",
        decision_value_digest="a" * 64,
    )
    assert result["status"] == "invalid"


# ── HTTP edge ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DECISION_SERVICE_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(main, "sor_enabled", lambda: True)
    monkeypatch.setattr(main, "agronomic_context_required", lambda: False)
    return main, TestClient(main.app)


def _headers():
    return {"Authorization": f"Bearer {TOKEN}", "X-Tenant-Id": TENANT, "X-Reviewed-By": "u-solo"}


def _body(**over):
    body = {
        "action": "approve",
        "candidate_lineage_id": "lin",
        "decision_value_digest": "a" * 64,
        "idempotency_key": "rev-1",
        "policy_version": "rev/1",
    }
    body.update(over)
    return body


def test_endpoint_forwards_the_acknowledgement(client, monkeypatch):
    main, http = client
    reviewer = AsyncMock(return_value={"status": "ok", "state": "approved"})
    monkeypatch.setattr(main, "review_decision", reviewer)
    result = http.post(
        "/v1/decisions/dec_r/review",
        headers=_headers(),
        json=_body(self_approval_acknowledged=True, self_approval_reason="solo farm"),
    )
    assert result.status_code == 200, result.text
    kwargs = reviewer.await_args.kwargs
    assert kwargs["self_approval_acknowledged"] is True
    assert kwargs["self_approval_reason"] == "solo farm"


def test_endpoint_defaults_to_no_acknowledgement(client, monkeypatch):
    main, http = client
    reviewer = AsyncMock(return_value={"status": "ok", "state": "approved"})
    monkeypatch.setattr(main, "review_decision", reviewer)
    assert (
        http.post("/v1/decisions/dec_r/review", headers=_headers(), json=_body()).status_code == 200
    )
    assert reviewer.await_args.kwargs["self_approval_acknowledged"] is False


def test_endpoint_refusal_names_the_independent_approver(client, monkeypatch):
    main, http = client
    _enable(monkeypatch)
    verdict = _verdict(decision_type="irrigation")
    monkeypatch.setattr(
        main,
        "review_decision",
        AsyncMock(
            return_value={
                "status": "forbidden",
                "reason": "separation_of_duties_violation",
                "refusal": verdict["refusal"],
                "message": verdict["message"],
            }
        ),
    )
    result = http.post("/v1/decisions/dec_r/review", headers=_headers(), json=_body())
    assert result.status_code == 403, result.text
    detail = result.json()["detail"]
    assert detail.startswith("separation_of_duties_violation (self_approval_excluded_operation)")
    assert "independent approver" in detail


def test_endpoint_rejects_a_client_forged_marker(client, monkeypatch):
    main, http = client
    from persistence import SELF_APPROVAL_REASON_PREFIX

    reviewer = AsyncMock()
    monkeypatch.setattr(main, "review_decision", reviewer)
    result = http.post(
        "/v1/decisions/dec_r/review",
        headers=_headers(),
        json=_body(reason=SELF_APPROVAL_REASON_PREFIX + "{}"),
    )
    assert result.status_code == 422, result.text
    reviewer.assert_not_awaited()
