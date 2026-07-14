from datetime import UTC, datetime, timedelta

import pytest
from api.irrigation_commissioning_runtime import (
    CommissioningCertificateInput,
    CommissioningState,
    CommissioningTest,
    CommissioningTestOutcome,
    authorize_execution,
    build_commissioning_certificate,
    transition_commissioning_state,
)

DIGEST = "a" * 64
REQUIRED = [
    "pump_curve",
    "operating_pressure",
    "actual_flow",
    "pressure_stability",
    "leak_and_pressure_collapse",
    "dry_run_protection",
    "voltage_drop",
    "frequency_stability",
    "essential_sensors",
    "emergency_stop",
    "controller_connectivity",
    "valve_state",
]


def _payload(*, fail=None, degraded=None, modes=None):
    now = datetime(2026, 7, 14, tzinfo=UTC)
    tests = []
    for i, kind in enumerate(REQUIRED):
        outcome = (
            CommissioningTestOutcome.FAIL
            if kind == fail
            else CommissioningTestOutcome.DEGRADED
            if kind == degraded
            else CommissioningTestOutcome.PASS
        )
        tests.append(
            CommissioningTest(
                test_id=f"t{i}",
                test_type=kind,
                outcome=outcome,
                tested_at=now,
                measured={"value": 1.0},
                design={"value": 1.0},
                evidence_digests=[DIGEST],
            )
        )
    return CommissioningCertificateInput(
        certificate_id="cert-1",
        tenant_id="11111111-1111-1111-1111-111111111111",
        field_id="fld-1",
        season_id="season-1",
        system_id="sys-1",
        machine_id="machine-1",
        pump_id="pump-1",
        controller_id="controller-1",
        specification_version="1",
        specification_digest=DIGEST,
        capability_graph_digest="b" * 64,
        commissioning_version=1,
        tested_at=now,
        valid_until=now + timedelta(days=365),
        tests=tests,
        safety_interlocks={
            "emergency_stop": True,
            "dry_run_protection": True,
            "overpressure_protection": True,
            "loss_of_communication_safe_state": True,
            "manual_override": True,
        },
        execution_limits={"max_flow_lps": 80},
        requested_execution_modes=modes or ["supervised", "automated"],
        issued_by="22222222-2222-2222-2222-222222222222",
        reviewed_by="33333333-3333-3333-3333-333333333333",
    )


def test_pass_certificate_allows_automation():
    cert = build_commissioning_certificate(_payload(), now=datetime(2026, 7, 14, tzinfo=UTC))
    assert cert.status == CommissioningState.PASS
    assert "automated" in cert.permitted_execution_modes
    auth = authorize_execution(
        requested_mode="automated",
        certificate=cert,
        now=datetime(2026, 7, 15, tzinfo=UTC),
        decision_approved=True,
        telemetry_fresh=True,
        blocking_alarm=False,
        execution_window_valid=True,
        adapter_capable=True,
    )
    assert auth.execution_allowed is True


def test_missing_or_failed_test_blocks_automation():
    cert = build_commissioning_certificate(
        _payload(fail="emergency_stop"), now=datetime(2026, 7, 14, tzinfo=UTC)
    )
    assert cert.status == CommissioningState.FAIL
    assert "automated" not in cert.permitted_execution_modes
    auth = authorize_execution(
        requested_mode="automated",
        certificate=cert,
        decision_approved=True,
        telemetry_fresh=True,
        blocking_alarm=False,
        execution_window_valid=True,
        adapter_capable=True,
    )
    assert auth.execution_allowed is False


def test_degraded_certificate_does_not_silently_certify_automated_mode():
    cert = build_commissioning_certificate(
        _payload(degraded="pressure_stability"), now=datetime(2026, 7, 14, tzinfo=UTC)
    )
    assert cert.status == CommissioningState.DEGRADED
    assert cert.warnings


def test_manual_mode_remains_available_without_certificate():
    auth = authorize_execution(
        requested_mode="manual_measured",
        certificate=None,
        decision_approved=True,
        telemetry_fresh=False,
        blocking_alarm=False,
        execution_window_valid=True,
        adapter_capable=False,
    )
    assert auth.manual_execution_allowed is True
    assert auth.execution_allowed is True


def test_automated_mode_requires_certificate_adapter_and_fresh_telemetry():
    auth = authorize_execution(
        requested_mode="automated",
        certificate=None,
        decision_approved=True,
        telemetry_fresh=False,
        blocking_alarm=False,
        execution_window_valid=True,
        adapter_capable=False,
    )
    assert auth.execution_allowed is False
    assert "VALID_COMMISSIONING_CERTIFICATE_REQUIRED" in auth.blocking_reasons
    assert "ADAPTER_NOT_CAPABLE" in auth.blocking_reasons
    assert "TELEMETRY_STALE" in auth.blocking_reasons


def test_state_machine_rejects_illegal_transition():
    assert (
        transition_commissioning_state(CommissioningState.DRAFT, CommissioningState.TESTING)
        == CommissioningState.TESTING
    )
    with pytest.raises(ValueError):
        transition_commissioning_state(CommissioningState.DRAFT, CommissioningState.PASS)


def test_digest_is_deterministic():
    a = build_commissioning_certificate(_payload(), now=datetime(2026, 7, 14, tzinfo=UTC))
    b = build_commissioning_certificate(_payload(), now=datetime(2026, 7, 14, tzinfo=UTC))
    assert a.certificate_digest == b.certificate_digest
