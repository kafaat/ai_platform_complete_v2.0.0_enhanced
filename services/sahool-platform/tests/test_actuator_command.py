"""اختبارات بناء أمر المُشغِّل (core.actuator_command) — نقيّ offline."""

import pytest
from core.actuator_command import build_actuator_command
from core.decision_dispatch import DispatchDecision, DispatchState

pytestmark = pytest.mark.unit


def _decision(state=DispatchState.READY, **kw):
    base = dict(
        state=state,
        recommendation_id="rec-7",
        action_type="irrigation",
        field_id="fld_1",
        risk_level="LOW",
        required_approvals=0,
        approvals_collected=0,
    )
    base.update(kw)
    return DispatchDecision(**base)


def test_build_for_ready_decision():
    cmd = build_actuator_command(
        _decision(), device_id="dev-9", command="open_valve", params={"duration_min": 30}
    )
    assert cmd.device_id == "dev-9"
    assert cmd.command == "open_valve"
    assert cmd.payload["duration_min"] == 30
    assert cmd.payload["field_id"] == "fld_1"  # أُضيف للأثر
    assert cmd.payload["recommendation_id"] == "rec-7"
    assert cmd.idempotency_key == "rec-7:open_valve:dev-9"
    assert "device_id" in cmd.to_dict()


def test_custom_idempotency_key_respected():
    cmd = build_actuator_command(
        _decision(), device_id="d", command="c", idempotency_key="custom-key"
    )
    assert cmd.idempotency_key == "custom-key"


def test_blocked_decision_refused():
    with pytest.raises(ValueError):
        build_actuator_command(
            _decision(state=DispatchState.BLOCKED), device_id="d", command="open_valve"
        )


def test_pending_decision_refused():
    with pytest.raises(ValueError):
        build_actuator_command(
            _decision(state=DispatchState.PENDING_APPROVAL, risk_level="HIGH"),
            device_id="d",
            command="open_valve",
        )


def test_missing_device_or_command_refused():
    with pytest.raises(ValueError):
        build_actuator_command(_decision(), device_id="", command="open_valve")
    with pytest.raises(ValueError):
        build_actuator_command(_decision(), device_id="d", command="  ")
