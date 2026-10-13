"""Historical scenario comparisons bind real measurement and verification evidence."""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import api.main  # noqa: F401
import pytest
from api.irrigation_manual_execution import (
    ManualExecutionConfirmation,
    ManualRecommendationInput,
    derive_manual_as_applied,
)
from api.irrigation_manual_ledger_bridge import ManualVerificationInput, verify_manual_as_applied
from api.outcome_measurement import compare_irrigation_executions
from api.routers import outcome
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException
from pydantic import ValidationError

pytestmark = pytest.mark.unit
BASELINE = "00000000-0000-0000-0000-000000000011"
CANDIDATE = "00000000-0000-0000-0000-000000000012"
USER = UserSchema(
    user_id="reader",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مقارنة",
)


def record(execution_id=BASELINE, volume=100.0, *, target_depth_mm=10, target_volume_m3=100):
    now = datetime.now(UTC) - timedelta(days=1)
    recommendation = ManualRecommendationInput(
        execution_id=execution_id,
        tenant_id=USER.tenant_id,
        field_id="f1",
        season_id="s1",
        system_id="sys1",
        recommendation_id="r1",
        recommendation_digest="a" * 64,
        mode="manual_measured",
        target_depth_mm=target_depth_mm,
        target_volume_m3=target_volume_m3,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        created_by="operator",
    )
    confirmation = ManualExecutionConfirmation(
        started_at=now - timedelta(hours=2),
        stopped_at=now,
        completion_ratio=1,
        meter_start_m3=0,
        meter_end_m3=volume,
        evidence_digests=["b" * 64],
        deviation_reason="اختلاف مقيس",
    )
    applied = derive_manual_as_applied(recommendation, confirmation).model_dump(mode="json")
    request = ManualVerificationInput(
        as_applied_digest=applied["as_applied_digest"],
        reviewer_id="independent",
        reviewed_at=now,
        evidence_digests=["b" * 64],
        volume_verified=True,
        timing_verified=True,
        field_verified=True,
    )
    verified = verify_manual_as_applied(
        execution_id=execution_id,
        stored_as_applied=applied,
        stored_as_applied_digest=applied["as_applied_digest"],
        execution_mode="manual_measured",
        confirmation=confirmation.model_dump(mode="json"),
        request=request,
    )
    return {
        "execution_id": execution_id,
        "field_id": "f1",
        "season_id": "s1",
        "system_id": "sys1",
        "execution_mode": "manual_measured",
        "state": "reconciled",
        "ledger_eligible": True,
        "target_depth_mm": target_depth_mm,
        "target_volume_m3": target_volume_m3,
        "as_applied": applied,
        "as_applied_digest": applied["as_applied_digest"],
        "verification": {**request.model_dump(mode="json"), **verified.model_dump(mode="json")},
        "verification_digest": verified.verification_digest,
    }


def test_measured_delta_is_descriptive_and_missing_cost_not_zero():
    baseline, candidate = record(), record(CANDIDATE, 80)
    out = compare_irrigation_executions(baseline, candidate)
    assert out["status"] == "measured_comparison"
    assert out["water"]["baseline_minus_candidate_m3"] == 20
    assert out["water"]["baseline_minus_candidate_mm"] == 2
    assert out["runtime"]["baseline_minus_candidate_hours"] == 0
    assert out["causal_effect"] == {"status": "not_established"}
    assert out["energy"] == {"status": "not_measured"}
    assert out["economics"] == {"status": "not_computed"}
    assert "savings" not in out
    assert out["evidence"] == {
        "baseline": {key: baseline[key] for key in ("as_applied_digest", "verification_digest")},
        "candidate": {key: candidate[key] for key in ("as_applied_digest", "verification_digest")},
    }


def test_more_water_keeps_signed_negative_delta():
    out = compare_irrigation_executions(record(), record(CANDIDATE, 120))
    assert out["water"]["baseline_minus_candidate_m3"] == -20


@pytest.mark.parametrize(
    "key,value,reason",
    [
        ("state", "confirmed", "RECONCILED_LEDGER_EVIDENCE_REQUIRED"),
        ("ledger_eligible", False, "RECONCILED_LEDGER_EVIDENCE_REQUIRED"),
        ("execution_mode", "manual_estimated", "MEASURED_WATER_EVIDENCE_REQUIRED"),
        ("season_id", "other", "SAME_SEASON_ID_REQUIRED"),
        ("system_id", "other", "SAME_SYSTEM_ID_REQUIRED"),
        ("field_id", "other", "SAME_FIELD_ID_REQUIRED"),
        ("target_volume_m3", 200, "SAME_AREA_REQUIRED"),
        ("target_depth_mm", 0, "POSITIVE_AREA_REQUIRED"),
        ("target_depth_mm", True, "POSITIVE_AREA_REQUIRED"),
        ("target_depth_mm", float("nan"), "POSITIVE_AREA_REQUIRED"),
        ("verification_digest", "c" * 64, "VERIFICATION_BINDING_REQUIRED"),
    ],
)
def test_incomparable_records_never_return_delta(key, value, reason):
    candidate = record(CANDIDATE, 80)
    candidate[key] = value
    out = compare_irrigation_executions(record(), candidate)
    assert out["status"] == "needs_data"
    assert any(reason in item for item in out["reasons"])
    assert all(value is None for value in out["water"].values())
    assert out["evidence"] == {"baseline": None, "candidate": None}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "80"])
def test_nonfinite_or_coerced_water_is_refused(value):
    candidate = record(CANDIDATE, 80)
    candidate["as_applied"]["actual_volume_m3"] = value
    out = compare_irrigation_executions(record(), candidate)
    assert out["status"] == "needs_data"
    assert "candidate:FINITE_POSITIVE_WATER_REQUIRED" in out["reasons"]
    assert "candidate:AS_APPLIED_DIGEST_MISMATCH" in out["reasons"]


def test_verification_cannot_be_reused_for_other_measurement():
    candidate = record(CANDIDATE, 80)
    candidate["verification"] = deepcopy(record()["verification"])
    candidate["verification_digest"] = candidate["verification"]["verification_digest"]
    out = compare_irrigation_executions(record(), candidate)
    assert "candidate:VERIFICATION_BINDING_REQUIRED" in out["reasons"]


def request(**updates):
    body = {
        "field_id": "f1",
        "planned": {},
        "actual": {},
        "irrigation_comparison": {
            "baseline_execution_id": BASELINE,
            "candidate_execution_id": CANDIDATE,
        },
    }
    return outcome.OutcomeRequest(**{**body, **updates})


def test_request_rejects_identical_ids_or_absent_field_or_client_quantities():
    with pytest.raises(ValidationError, match="DISTINCT_EXECUTIONS_REQUIRED"):
        request(
            irrigation_comparison={
                "baseline_execution_id": BASELINE,
                "candidate_execution_id": BASELINE,
            }
        )
    with pytest.raises(ValidationError, match="COMPARISON_FIELD_REQUIRED"):
        request(field_id=None)
    with pytest.raises(ValidationError):
        request(
            irrigation_comparison={
                "baseline_execution_id": BASELINE,
                "candidate_execution_id": CANDIDATE,
                "actual_volume_m3": 80,
            }
        )


async def test_endpoint_scopes_both_records_and_never_writes(monkeypatch):
    calls = []

    class Connection:
        async def fetch(self, sql, *args):
            calls.append((sql, args))
            return [record(), record(CANDIDATE, 80)]

    @asynccontextmanager
    async def connection(user):
        assert user is USER
        yield Connection()

    monkeypatch.setattr(outcome, "tenant_connection", connection)
    out = await outcome.measure_decision_outcome(request(), USER)
    sql, args = calls[0]
    assert "tenant_id=$1::uuid AND field_id=$2" in sql
    assert "execution_id=ANY($3::uuid[])" in sql
    assert args == (USER.tenant_id, "f1", [UUID(BASELINE), UUID(CANDIDATE)])
    assert len(calls) == 1
    assert out["irrigation_comparison"]["status"] == "measured_comparison"


async def test_foreign_or_missing_evidence_has_same_404(monkeypatch):
    class Connection:
        async def fetch(self, *args):
            return [record()]

    @asynccontextmanager
    async def connection(user):
        yield Connection()

    monkeypatch.setattr(outcome, "tenant_connection", connection)
    with pytest.raises(HTTPException) as exc:
        await outcome.measure_decision_outcome(request(), USER)
    assert exc.value.status_code == 404
    assert exc.value.detail == "IRRIGATION_COMPARISON_EVIDENCE_NOT_FOUND"


async def test_comparison_permission_denied_before_database(monkeypatch):
    def deny(_permission):
        def check(_user):
            raise HTTPException(status_code=403, detail="denied")

        return check

    def no_database(_user):
        raise AssertionError("database accessed before permission")

    monkeypatch.setattr(outcome, "require_permission", deny)
    monkeypatch.setattr(outcome, "tenant_connection", no_database)
    with pytest.raises(HTTPException) as exc:
        await outcome.measure_decision_outcome(request(), USER)
    assert exc.value.status_code == 403


async def test_legacy_request_never_reads_database(monkeypatch):
    def no_database(_user):
        raise AssertionError("legacy database access")

    monkeypatch.setattr(outcome, "tenant_connection", no_database)
    out = await outcome.measure_decision_outcome(request(irrigation_comparison=None), USER)
    assert "irrigation_comparison" not in out
    assert "metrics" in out


@pytest.mark.parametrize("value", ["[1]", "null", "{bad", [], None, 123])
@pytest.mark.parametrize("key", ["as_applied", "verification"])
def test_malformed_stored_evidence_is_missing_not_exception(key, value):
    candidate = record(CANDIDATE, 80)
    candidate[key] = value
    out = compare_irrigation_executions(record(), candidate)
    assert out["status"] == "needs_data"
    assert out["water"]["baseline_minus_candidate_m3"] is None
    assert len(out["warnings_ar"]) > 3


def test_huge_integer_water_is_refused_without_overflow():
    candidate = record(CANDIDATE, 80)
    candidate["target_volume_m3"] = 10**400
    out = compare_irrigation_executions(record(), candidate)
    assert out["status"] == "needs_data"
    assert "candidate:POSITIVE_AREA_REQUIRED" in out["reasons"]


@pytest.mark.parametrize(
    "key, value",
    [
        ("quality", []),
        pytest.param("actual_volume_m3", 10**5000, id="huge-volume"),
    ],
)
def test_malformed_evidence_values_fail_closed(key, value):
    candidate = record(CANDIDATE, 80)
    candidate["as_applied"][key] = value
    out = compare_irrigation_executions(record(), candidate)
    assert out["status"] == "needs_data"


@pytest.mark.parametrize("reviewed_at", ["bad", "2026-10-01T12:00:00", None])
def test_verification_requires_aware_time_bound_to_verified_at(reviewed_at):
    candidate = record(CANDIDATE, 80)
    candidate["verification"]["reviewed_at"] = reviewed_at
    out = compare_irrigation_executions(record(), candidate)
    assert "candidate:VERIFICATION_BINDING_REQUIRED" in out["reasons"]


async def test_database_failure_is_sanitized_unavailable_not_missing(monkeypatch):
    @asynccontextmanager
    async def unavailable(user):
        raise RuntimeError("private database details")
        yield

    monkeypatch.setattr(outcome, "tenant_connection", unavailable)
    with pytest.raises(HTTPException) as exc:
        await outcome.measure_decision_outcome(request(), USER)
    assert exc.value.status_code == 503
    assert "private database details" not in str(exc.value.detail)


def test_large_area_accepts_real_builder_depth_volume_quantization():
    baseline = record(target_depth_mm=1, target_volume_m3=100)
    candidate = record(CANDIDATE, 20.006, target_depth_mm=1, target_volume_m3=100)
    assert candidate["as_applied"]["actual_depth_mm"] == 0.2001
    assert candidate["as_applied"]["actual_volume_m3"] == 20.006
    out = compare_irrigation_executions(baseline, candidate)
    assert out["status"] == "measured_comparison"
    assert out["water"]["baseline_minus_candidate_m3"] == 79.994
    assert not any("WATER_AREA_INCONSISTENT" in reason for reason in out["reasons"])


def test_area_quantization_tolerance_still_refuses_inconsistent_water():
    baseline = record(target_depth_mm=1, target_volume_m3=100)
    candidate = record(CANDIDATE, 20.006, target_depth_mm=1, target_volume_m3=100)
    # Alter the stored area after deriving and verifying real measurements.
    # Both areas still match each other; their quantities contradict that area
    # by much more than the combined volume/depth quantization uncertainty.
    baseline["target_volume_m3"] = 101
    candidate["target_volume_m3"] = 101
    out = compare_irrigation_executions(baseline, candidate)
    assert out["status"] == "needs_data"
    assert "candidate:WATER_AREA_INCONSISTENT" in out["reasons"]
    assert "SAME_AREA_REQUIRED" not in out["reasons"]
    assert out["water"]["baseline_minus_candidate_m3"] is None
    assert out["evidence"] == {"baseline": None, "candidate": None}
