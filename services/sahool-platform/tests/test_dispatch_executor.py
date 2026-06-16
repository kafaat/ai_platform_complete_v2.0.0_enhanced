"""اختبارات منسّق تنفيذ القرار (core.dispatch_executor) — نقيّ، منفذ وهميّ.

العقد الأمنيّ: READY فقط يُدرَج للطابور؛ BLOCKED/PENDING يُسجَّل ولا يُنفَّذ. يتحقّق
بمنفذ persist وهميّ يرصد ما كُتب — بلا قاعدة.
"""

import pytest
from core.actuator_command import build_actuator_command
from core.decision_dispatch import DispatchDecision, DispatchState
from core.dispatch_executor import ExecutionStatus, execute_dispatch

pytestmark = pytest.mark.unit


def _decision(state=DispatchState.READY, **kw):
    base = dict(
        state=state,
        recommendation_id="rec-1",
        action_type="irrigation",
        field_id="fld_1",
        risk_level="LOW",
        required_approvals=0,
        approvals_collected=0,
    )
    base.update(kw)
    return DispatchDecision(**base)


class _FakePersist:
    """يرصد نداءات الإدامة: (decision, command, exec_status)."""

    def __init__(self):
        self.calls = []

    async def __call__(self, decision, command, exec_status):
        self.calls.append((decision, command, exec_status))


async def test_ready_decision_queued():
    persist = _FakePersist()
    cmd = build_actuator_command(_decision(), device_id="d1", command="open_valve")
    res = await execute_dispatch(_decision(), persist=persist, command=cmd)
    assert res.status == ExecutionStatus.QUEUED
    assert res.command["device_id"] == "d1"
    # سُجِّل بحالة queued مع الأمر
    assert len(persist.calls) == 1
    _, recorded_cmd, status = persist.calls[0]
    assert status == "queued"
    assert recorded_cmd["command"] == "open_valve"


async def test_blocked_decision_recorded_not_executed():
    persist = _FakePersist()
    res = await execute_dispatch(
        _decision(state=DispatchState.BLOCKED, halt_breaches=["pesticide_phi"]),
        persist=persist,
    )
    assert res.status == ExecutionStatus.NOT_EXECUTED
    assert res.command is None
    _, recorded_cmd, status = persist.calls[0]
    assert status == "not_executed" and recorded_cmd is None


async def test_pending_decision_recorded_not_executed():
    persist = _FakePersist()
    res = await execute_dispatch(
        _decision(state=DispatchState.PENDING_APPROVAL, risk_level="HIGH", required_approvals=2),
        persist=persist,
    )
    assert res.status == ExecutionStatus.NOT_EXECUTED
    assert persist.calls[0][2] == "not_executed"


async def test_ready_without_command_raises():
    persist = _FakePersist()
    with pytest.raises(ValueError):
        await execute_dispatch(_decision(), persist=persist, command=None)
    assert persist.calls == []  # لم يُدِم شيئاً قبل الخطأ


async def test_result_serializable():
    persist = _FakePersist()
    cmd = build_actuator_command(_decision(), device_id="d", command="c")
    res = await execute_dispatch(_decision(), persist=persist, command=cmd)
    import json

    assert json.dumps(res.to_dict(), ensure_ascii=False)
    assert res.to_dict()["status"] == "queued"
