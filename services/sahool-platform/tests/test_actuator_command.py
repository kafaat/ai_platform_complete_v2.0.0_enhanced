"""اختبارات بناء أمر المُشغِّل (core.actuator_command) — نقيّ offline."""

import pytest
from core.actuator_command import build_actuator_command, canonical_duration_payload
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
    # المصدرُ المعروف يحوّل الدقائق صراحةً إلى الحقل الكنسيّ — لا تمرير `duration_min` للمُشغِّل.
    assert cmd.payload["duration_sec"] == 1800
    assert "duration_min" not in cmd.payload
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


# ── `duration_sec` كنسيّ: هذا هو المصدر المعروف الوحيد لتحويل الدقائق ──
@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"duration_minutes": 10}, {"duration_sec": 600}),
        ({"duration_min": 1.5}, {"duration_sec": 90}),
        ({"durationMinutes": 0.25}, {"duration_sec": 15}),
        ({"duration_minutes": 10, "duration_sec": 600}, {"duration_sec": 600}),
        ({"duration_min": 5, "duration_minutes": 5}, {"duration_sec": 300}),
        ({"duration_sec": 45}, {"duration_sec": 45}),
        ({"duration_minutes": None}, {}),
        ({}, {}),
    ],
)
def test_minutes_are_converted_explicitly_to_duration_sec(params, expected):
    assert canonical_duration_payload(params) == expected


@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"duration_minutes": 10, "duration_sec": 60}, "conflicting_duration_fields"),
        ({"duration_min": 5, "duration_minutes": 6}, "conflicting_duration_fields"),
        ({"duration_minutes": 10, "duration_sec": "600"}, "conflicting_duration_fields"),
        ({"duration_minutes": 0}, "invalid_duration_minutes:duration_minutes"),
        ({"duration_minutes": -3}, "invalid_duration_minutes:duration_minutes"),
        ({"duration_min": "30"}, "invalid_duration_minutes:duration_min"),
        ({"duration_min": True}, "invalid_duration_minutes:duration_min"),
        ({"durationMinutes": float("nan")}, "invalid_duration_minutes:durationMinutes"),
    ],
)
def test_conflicting_or_invalid_minutes_are_refused_by_name(params, reason):
    with pytest.raises(ValueError) as exc:
        canonical_duration_payload(params)
    assert str(exc.value) == reason


def test_no_duration_is_never_defaulted():
    """لا 30 دقيقة افتراضيّة: أمرٌ بلا مدّة يبقى بلا مدّة ويرفض المُشغِّلُ فتحَه."""
    cmd = build_actuator_command(_decision(), device_id="dev-9", command="open_valve")
    assert "duration_sec" not in cmd.payload


def test_build_refuses_conflicting_durations_before_a_command_exists():
    with pytest.raises(ValueError, match="conflicting_duration_fields"):
        build_actuator_command(
            _decision(),
            device_id="dev-9",
            command="open_valve",
            params={"duration_sec": 60, "duration_minutes": 10},
        )
