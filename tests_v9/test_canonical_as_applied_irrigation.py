import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1] / "services" / "sahool-platform" / "api"
sys.path.insert(0, str(API))

from canonical_as_applied_irrigation import (  # noqa: E402
    as_applied_truth_to_water_ledger_event,
    build_as_applied_observation,
    build_authorized_irrigation_plan,
    build_canonical_as_applied_irrigation_truth,
    build_execution_receipt,
)

H = "a" * 64
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def plan():
    return build_authorized_irrigation_plan(
        tenant_id="tenant-1",
        field_id="field-1",
        season_id="season-1",
        machine_id="machine-1",
        controller_id="controller-1",
        decision_id="decision-1",
        authorization_id="auth-1",
        execution_plan_id="exec-1",
        planned_start_at=NOW - timedelta(minutes=20),
        planned_end_at=NOW - timedelta(minutes=5),
        planned_depth_mm=9,
        planned_volume_m3=900,
        planned_area_ha=10,
        irrigation_capability_digest=H,
        commissioning_certification_digest="b" * 64,
        decision_content_digest="c" * 64,
    )


def receipts(state="completed"):
    return [
        build_execution_receipt(
            tenant_id="tenant-1",
            field_id="field-1",
            machine_id="machine-1",
            controller_id="controller-1",
            execution_plan_id="exec-1",
            receipt_id="r1",
            state="running",
            sequence_number=1,
            observed_at=NOW - timedelta(minutes=20),
            controller_command_digest=H,
            payload_digest="d" * 64,
        ),
        build_execution_receipt(
            tenant_id="tenant-1",
            field_id="field-1",
            machine_id="machine-1",
            controller_id="controller-1",
            execution_plan_id="exec-1",
            receipt_id="r2",
            state=state,
            sequence_number=2,
            observed_at=NOW - timedelta(minutes=2),
            controller_command_digest=H,
            payload_digest="e" * 64,
        ),
    ]


def observations(flow=50.0, runtime=300.0, last_position=100.0):
    specs = [
        ("flow", flow, "lps", 1, 10),
        ("pressure", 2.5, "bar", 2, 9),
        ("runtime", runtime, "minutes", 3, 8),
        ("position", 0.0, "percent", 4, 7),
        ("position", last_position, "percent", 5, 1),
    ]
    return [
        build_as_applied_observation(
            tenant_id="tenant-1",
            field_id="field-1",
            machine_id="machine-1",
            controller_id="controller-1",
            execution_plan_id="exec-1",
            observation_type=kind,
            sequence_number=seq,
            observed_at=NOW - timedelta(minutes=minutes),
            value=value,
            unit=unit,
            source_message_id=f"m-{seq}",
            payload_digest=str(seq) * 64,
        )
        for kind, value, unit, seq, minutes in specs
    ]


def test_verified_as_applied_truth_and_ledger_event():
    truth = build_canonical_as_applied_irrigation_truth(
        plan=plan(), receipts=receipts(), observations=observations(), now=NOW
    )
    assert truth.status == "verified"
    assert truth.water_ledger_eligible is True
    assert round(truth.actual_volume_m3, 3) == 900
    assert round(truth.actual_depth_mm, 3) == 9
    assert truth.source_lineage["authorization_id"] == "auth-1"
    assert len(truth.as_applied_digest) == 64
    event = as_applied_truth_to_water_ledger_event(truth)
    assert event["status"] == "available"
    assert event["source"] == "measured_as_applied_truth"
    assert len(event["ledger_event_digest"]) == 64


def test_missing_terminal_receipt_blocks():
    truth = build_canonical_as_applied_irrigation_truth(
        plan=plan(), receipts=receipts()[:1], observations=observations(), now=NOW
    )
    assert "TERMINAL_EXECUTION_RECEIPT_REQUIRED" in truth.blocking_reasons
    assert truth.water_ledger_eligible is False


def test_failed_receipt_blocks():
    truth = build_canonical_as_applied_irrigation_truth(
        plan=plan(), receipts=receipts("failed"), observations=observations(), now=NOW
    )
    assert "EXECUTION_FAILED" in truth.blocking_reasons


def test_large_volume_variance_blocks_ledger():
    truth = build_canonical_as_applied_irrigation_truth(
        plan=plan(), receipts=receipts(), observations=observations(flow=25), now=NOW
    )
    assert "AS_APPLIED_VOLUME_VARIANCE_EXCEEDS_TOLERANCE" in truth.blocking_reasons
    assert as_applied_truth_to_water_ledger_event(truth)["status"] == "blocked"


def test_insufficient_position_coverage_blocks():
    truth = build_canonical_as_applied_irrigation_truth(
        plan=plan(), receipts=receipts(), observations=observations(last_position=50), now=NOW
    )
    assert "POSITION_COVERAGE_BELOW_ACCEPTANCE_THRESHOLD" in truth.blocking_reasons


def test_stale_telemetry_blocks():
    truth = build_canonical_as_applied_irrigation_truth(
        plan=plan(),
        receipts=receipts(),
        observations=observations(),
        now=NOW + timedelta(hours=2),
        maximum_telemetry_age_minutes=30,
    )
    assert "AS_APPLIED_TELEMETRY_STALE" in truth.blocking_reasons


def test_identity_mismatch_blocks():
    bad = observations()
    bad[0] = build_as_applied_observation(
        tenant_id="tenant-2",
        field_id="field-1",
        machine_id="machine-1",
        controller_id="controller-1",
        execution_plan_id="exec-1",
        observation_type="flow",
        sequence_number=1,
        observed_at=NOW - timedelta(minutes=10),
        value=50,
        unit="lps",
        source_message_id="bad",
        payload_digest="f" * 64,
    )
    truth = build_canonical_as_applied_irrigation_truth(
        plan=plan(), receipts=receipts(), observations=bad, now=NOW
    )
    assert "AS_APPLIED_OBSERVATION_IDENTITY_MISMATCH" in truth.blocking_reasons


pytestmark = pytest.mark.unit
