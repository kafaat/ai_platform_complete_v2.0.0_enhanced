from datetime import UTC, datetime, timedelta, timezone

import pytest
from api.controller_edge_adapter import (
    build_controller_capability_snapshot,
    build_controller_handshake,
    controller_capability_to_graph_input,
    normalize_controller_telemetry,
    prepare_controller_command_request,
)

NOW = datetime(2026, 7, 13, 12, tzinfo=UTC)


def handshake(mode="read_only", certified="certified"):
    return build_controller_handshake(
        tenant_id="t1",
        controller_id="c1",
        machine_id="m1",
        protocol="mqtt",
        provider="generic",
        model="x",
        firmware_version="1.2.3",
        integration_mode=mode,
        capabilities={"read_status": True, "read_position": True, "start_stop": True},
        certification_status=certified,
        identity_fingerprint="abcdef0123456789",
        observed_at=NOW,
    )


def telemetry(h, seq=1, observed=NOW, alarms=None):
    return normalize_controller_telemetry(
        handshake=h,
        payload={
            "connection_status": "online",
            "operating_state": "idle",
            "position_percent": 25,
            "speed_percent": 50,
            "pressure_bar": 2.1,
            "flow_lps": 40,
            "alarm_codes": alarms or [],
        },
        sequence_number=seq,
        observed_at=observed,
        received_at=NOW + timedelta(seconds=1),
        source_message_id=f"msg-{seq}",
    )


def test_verified_read_only_snapshot_and_graph_contract():
    h = handshake()
    t = telemetry(h)
    s = build_controller_capability_snapshot(
        handshake=h, telemetry=t, now=NOW + timedelta(seconds=2)
    )
    assert s.status == "verified" and s.operational_eligible
    assert "READ_ONLY_NO_COMMAND_EXECUTION" in s.limitations
    graph = controller_capability_to_graph_input(s)
    assert len(graph["capability_digest"]) == 64 and graph["telemetry_fresh"]


def test_replay_sequence_is_rejected():
    h = handshake()
    with pytest.raises(ValueError, match="REPLAY"):
        normalize_controller_telemetry(
            handshake=h,
            payload={},
            sequence_number=5,
            observed_at=NOW,
            received_at=NOW,
            source_message_id="m",
            previous_sequence_number=5,
        )


def test_stale_telemetry_blocks_capability():
    h = handshake()
    t = telemetry(h, observed=NOW - timedelta(minutes=10))
    s = build_controller_capability_snapshot(
        handshake=h, telemetry=t, now=NOW, maximum_age_seconds=300
    )
    assert not s.operational_eligible and "CONTROLLER_TELEMETRY_STALE" in s.blocking_reasons


def test_active_alarm_blocks_capability():
    h = handshake()
    t = telemetry(h, alarms=["LOW_PRESSURE"])
    s = build_controller_capability_snapshot(handshake=h, telemetry=t, now=NOW)
    assert "CONTROLLER_ACTIVE_ALARM" in s.blocking_reasons


def test_read_only_never_prepares_command():
    h = handshake()
    t = telemetry(h)
    s = build_controller_capability_snapshot(handshake=h, telemetry=t, now=NOW)
    with pytest.raises(PermissionError, match="FORBIDS"):
        prepare_controller_command_request(
            snapshot=s, command_type="start", parameters={}, decision_id="d1", authorization_id="a1"
        )


def test_authorized_mode_prepares_non_dispatchable_envelope():
    h = handshake(mode="human_approved_control")
    t = telemetry(h)
    s = build_controller_capability_snapshot(handshake=h, telemetry=t, now=NOW)
    req = prepare_controller_command_request(
        snapshot=s,
        command_type="start",
        parameters={"speed_percent": 50},
        decision_id="d1",
        authorization_id="a1",
    )
    assert req["dispatch_allowed"] is False and len(req["command_request_digest"]) == 64


def test_authorization_is_required():
    h = handshake(mode="guarded_automation")
    t = telemetry(h)
    s = build_controller_capability_snapshot(handshake=h, telemetry=t, now=NOW)
    with pytest.raises(PermissionError, match="AUTHORIZATION"):
        prepare_controller_command_request(
            snapshot=s, command_type="start", parameters={}, decision_id="d1", authorization_id=None
        )


pytestmark = pytest.mark.unit
