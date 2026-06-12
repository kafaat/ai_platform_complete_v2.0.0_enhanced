"""اختبارات مُوجِّه الأوامر (offline) — تسجيل + توجيه + idempotency + دورة الحياة.

يُختبَر بمتجر ذاكرة وهميّ (عقد get/save/mark_*) بلا قاعدة. يتحقّق من: منع
التسجيل المكرّر، رفض الأمر المجهول، نجاح المعالِج + mark_succeeded، فشل المعالِج +
mark_failed، وidempotency (أمر مُنفَّذ سابقاً → was_duplicate بلا إعادة تنفيذ).
"""

import asyncio

import pytest
from api.command_dispatcher import CommandRegistry, dispatch
from api.command_store import Command, CommandStatus


class _FakeStore:
    """متجر ذاكرة وهميّ يطابق عقد CommandStore (get/save/mark_*)."""

    def __init__(self):
        self.cmds: dict[str, Command] = {}
        self.saved_calls = 0

    async def get(self, command_id):
        return self.cmds.get(command_id)

    async def save(self, cmd):  # ON CONFLICT DO NOTHING المحاكى
        self.saved_calls += 1
        self.cmds.setdefault(cmd.command_id, cmd)

    async def mark_processing(self, command_id):
        self.cmds[command_id].status = CommandStatus.PROCESSING

    async def mark_succeeded(self, command_id, result):
        c = self.cmds[command_id]
        c.status = CommandStatus.SUCCEEDED
        c.result = result

    async def mark_failed(self, command_id, error):
        c = self.cmds[command_id]
        c.status = CommandStatus.FAILED
        c.error = error


def _cmd(ctype="CreateField", cid="cmd-1"):
    return Command.new(ctype, actor_id="u1", tenant_id="t1", payload={"x": 1}, command_id=cid)


# ─── السجلّ ──────────────────────────────────────────────────────────────


def test_register_then_lookup():
    reg = CommandRegistry()

    async def h(cmd):
        return {"ok": True}

    reg.register("CreateField", h)
    assert reg.handler_for("CreateField") is h
    assert reg.registered_types() == ["CreateField"]


def test_duplicate_registration_rejected():
    reg = CommandRegistry()

    async def h(cmd):
        return {}

    reg.register("CreateField", h)
    with pytest.raises(ValueError):  # توجيه غامض ممنوع
        reg.register("CreateField", h)


# ─── التوجيه + دورة الحياة ───────────────────────────────────────────────


def test_dispatch_success_marks_succeeded():
    reg = CommandRegistry()
    calls = []

    async def h(cmd):
        calls.append(cmd.command_id)
        return {"field_id": "f1"}

    reg.register("CreateField", h)
    store = _FakeStore()
    res = asyncio.run(dispatch(reg, store, _cmd()))
    assert res.status == CommandStatus.SUCCEEDED
    assert res.result == {"field_id": "f1"}
    assert calls == ["cmd-1"]  # نُفِّذ مرّة
    assert store.cmds["cmd-1"].status == CommandStatus.SUCCEEDED


def test_dispatch_unknown_command_fails_without_execution():
    reg = CommandRegistry()  # لا معالِجات
    store = _FakeStore()
    res = asyncio.run(dispatch(reg, store, _cmd("UnknownCmd")))
    assert res.status == CommandStatus.FAILED
    assert "لا معالِج" in res.error
    assert store.saved_calls == 0  # لم يُحفظ أمر بلا معالِج


def test_dispatch_handler_error_marks_failed():
    reg = CommandRegistry()

    async def boom(cmd):
        raise RuntimeError("فشل المعالِج")

    reg.register("CreateField", boom)
    store = _FakeStore()
    res = asyncio.run(dispatch(reg, store, _cmd()))
    assert res.status == CommandStatus.FAILED
    assert "فشل المعالِج" in res.error
    assert store.cmds["cmd-1"].status == CommandStatus.FAILED


# ─── idempotency ─────────────────────────────────────────────────────────


def test_idempotent_redispatch_returns_duplicate_without_reexecution():
    reg = CommandRegistry()
    calls = []

    async def h(cmd):
        calls.append(1)
        return {"n": len(calls)}

    reg.register("CreateField", h)
    store = _FakeStore()
    first = asyncio.run(dispatch(reg, store, _cmd()))
    second = asyncio.run(dispatch(reg, store, _cmd()))  # نفس command_id
    assert first.was_duplicate is False
    assert second.was_duplicate is True  # لم يُنفَّذ ثانيةً
    assert second.result == first.result  # النتيجة المخزّنة
    assert len(calls) == 1  # المعالِج نُفِّذ مرّة واحدة فقط
