from datetime import UTC, datetime, timedelta

import pytest
from api.irrigation_manual_ledger_bridge import (
    ManualVerificationInput,
    build_manual_water_ledger_event,
    verify_manual_as_applied,
)

pytestmark = pytest.mark.unit

D = "a" * 64
E = "b" * 64


def request(**overrides):
    data = dict(
        as_applied_digest=D,
        reviewer_id="reviewer-1",
        reviewed_at=datetime.now(UTC) - timedelta(minutes=1),
        evidence_digests=[E],
        volume_verified=True,
        timing_verified=True,
        field_verified=True,
    )
    data.update(overrides)
    return ManualVerificationInput(**data)


def test_measured_confirmation_can_be_independently_verified():
    result = verify_manual_as_applied(
        execution_id="11111111-1111-1111-1111-111111111111",
        stored_as_applied={"quality": "measured_meter", "ledger_eligible": True},
        stored_as_applied_digest=D,
        execution_mode="manual_measured",
        confirmation={"evidence_digests": [E]},
        request=request(),
    )
    assert result.status == "verified"
    assert result.ledger_eligible is True
    assert len(result.verification_digest) == 64


def test_estimated_execution_cannot_be_verified_for_ledger():
    result = verify_manual_as_applied(
        execution_id="11111111-1111-1111-1111-111111111111",
        stored_as_applied={"quality": "estimated", "ledger_eligible": False},
        stored_as_applied_digest=D,
        execution_mode="manual_estimated",
        confirmation={"evidence_digests": [E]},
        request=request(),
    )
    assert result.status == "rejected"
    assert "ONLY_MANUAL_MEASURED_CAN_BE_VERIFIED_FOR_LEDGER" in result.blocking_reasons


def test_digest_mismatch_fails_closed():
    result = verify_manual_as_applied(
        execution_id="11111111-1111-1111-1111-111111111111",
        stored_as_applied={"quality": "measured_flow", "ledger_eligible": True},
        stored_as_applied_digest="c" * 64,
        execution_mode="manual_measured",
        confirmation={"evidence_digests": [E]},
        request=request(),
    )
    assert "AS_APPLIED_DIGEST_MISMATCH" in result.blocking_reasons


def test_ledger_event_requires_verified_state():
    with pytest.raises(ValueError, match="MANUAL_EXECUTION_NOT_VERIFIED"):
        build_manual_water_ledger_event(
            execution={"state": "confirmed", "ledger_eligible": True},
            verification_digest="c" * 64,
        )


def test_verified_measured_execution_builds_digest_bound_ledger_event():
    event = build_manual_water_ledger_event(
        execution={
            "execution_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "field_id": "fld-1",
            "season_id": "season-1",
            "state": "verified",
            "ledger_eligible": True,
            "as_applied": {"actual_volume_m3": 1000, "actual_depth_mm": 2.0},
            "confirmation": {"stopped_at": "2026-07-14T12:00:00+00:00"},
            "as_applied_digest": D,
        },
        verification_digest="c" * 64,
    )
    assert event.applied_volume_m3 == 1000
    assert event.applied_depth_mm == 2.0
    assert len(event.ledger_event_digest) == 64
