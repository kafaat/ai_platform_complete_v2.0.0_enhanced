"""
tests_v9/test_command_store_behavior_v66.py — سلوكيّات CommandDispatcher / CommandStore (A3).

Pure logic (مخزن وهميّ في الذاكرة يطابق عقد CommandStore) — لا DB.
يكمّل v65 (الذي يغطّي: الحلقة اللانهائيّة لـFAILED، التنفيذ المزدوج المتزامن،
وتجاوز MAX_RETRIES). هنا نغطّي سلوكيّات أخرى:
  - idempotency لأمر SUCCEEDED (نتيجة مخزّنة، was_duplicate، بلا إعادة تنفيذ).
  - أمر PROCESSING قائم ⇒ PROCESSING/was_duplicate بلا تنفيذ.
  - لا معالِج مُسجَّل ⇒ FAILED مع رسالة + الأمر يُعلَّم failed.
  - register: تكرار النوع يرفع ValueError؛ registered_types يُرجِع المسجّل.
  - حقول DispatchResult في كلّ مسار.
  - Command.new يولّد قيماً سليمة.
"""

import asyncio
import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from api.command_store import (  # noqa: E402
    Command,
    CommandDispatcher,
    CommandSource,
    CommandStatus,
    DispatchResult,
)


class FakeStore:
    """مخزن أوامر وهميّ يطابق عقد CommandStore الذي يستعمله CommandDispatcher.

    العقد: get / insert / mark_processing (ذرّيّ يُرجِع bool) /
    mark_succeeded / mark_failed. يحتفظ بـ(status, result, error, retry_count)
    لكلّ أمر، ويحاكي حارس الحالة الذرّيّ pending|failed → processing.
    """

    def __init__(self):
        self._rows = {}  # command_id -> dict(status, result, error, retry_count)
        self.exec_count = 0

    def seed(self, command_id, status, result=None, error=None, retry_count=0):
        self._rows[command_id] = {
            "status": status,
            "result": result,
            "error": error,
            "retry_count": retry_count,
        }

    async def get(self, command_id):
        row = self._rows.get(command_id)
        if row is None:
            return None
        return Command(
            command_id=command_id,
            command_type="t",
            actor_id="a",
            tenant_id="00000000-0000-0000-0000-000000000000",
            payload={},
            source=CommandSource.SCHEDULER,
            status=row["status"],
            result=row["result"],
            error=row["error"],
            retry_count=row["retry_count"],
        )

    async def insert(self, cmd):
        if cmd.command_id in self._rows:
            return False
        self._rows[cmd.command_id] = {
            "status": CommandStatus.PENDING,
            "result": None,
            "error": None,
            "retry_count": 0,
        }
        return True

    async def mark_processing(self, command_id):
        row = self._rows.get(command_id)
        if row is not None and row["status"] in (CommandStatus.PENDING, CommandStatus.FAILED):
            row["status"] = CommandStatus.PROCESSING
            return True
        return False

    async def mark_succeeded(self, command_id, result):
        row = self._rows[command_id]
        row["status"] = CommandStatus.SUCCEEDED
        row["result"] = result
        row["error"] = None

    async def mark_failed(self, command_id, error):
        row = self._rows[command_id]
        row["status"] = CommandStatus.FAILED
        row["error"] = error
        row["retry_count"] += 1


def _cmd(command_id="cmd-1", command_type="t"):
    return Command(
        command_id=command_id,
        command_type=command_type,
        actor_id="a",
        tenant_id="00000000-0000-0000-0000-000000000000",
        payload={"k": "v"},
        source=CommandSource.MOBILE,
    )


def _ok_handler(store, payload=None):
    async def handler(cmd):
        store.exec_count += 1
        return payload if payload is not None else {"ok": True}

    return handler


# ─── idempotency: أمر SUCCEEDED قائم ──────────────────────────────


def test_succeeded_command_returns_cached_result_without_reexecution():
    """إعادة أمر SUCCEEDED ⇒ النتيجة المخزّنة + was_duplicate، بلا إعادة تنفيذ المعالِج."""
    store = FakeStore()
    cached = {"id": 42, "done": True}
    store.seed("cmd-1", CommandStatus.SUCCEEDED, result=cached)
    disp = CommandDispatcher(store)
    disp.register("t", _ok_handler(store, payload={"fresh": True}))

    res = asyncio.run(disp.dispatch(_cmd("cmd-1")))

    assert res.status == CommandStatus.SUCCEEDED
    assert res.result == cached  # النتيجة المخزّنة لا الجديدة
    assert res.was_duplicate is True
    assert res.error is None
    assert store.exec_count == 0  # لم يُستدعَ المعالِج


# ─── أمر PROCESSING قائم ──────────────────────────────────────────


def test_processing_command_returns_processing_without_execution():
    """أمر قيد التنفيذ (عامل آخر) ⇒ PROCESSING/was_duplicate بلا تنفيذ."""
    store = FakeStore()
    store.seed("cmd-1", CommandStatus.PROCESSING)
    disp = CommandDispatcher(store)
    disp.register("t", _ok_handler(store))

    res = asyncio.run(disp.dispatch(_cmd("cmd-1")))

    assert res.status == CommandStatus.PROCESSING
    assert res.was_duplicate is True
    assert res.result is None
    assert store.exec_count == 0  # لم يُنفَّذ — مملوك لعامل آخر
    assert store._rows["cmd-1"]["status"] == CommandStatus.PROCESSING  # بلا تغيير


# ─── لا معالِج مُسجَّل ─────────────────────────────────────────────


def test_no_handler_marks_failed_with_message():
    """نوع أمر بلا معالِج ⇒ DispatchResult.FAILED مع رسالة، والأمر يُعلَّم failed."""
    store = FakeStore()
    disp = CommandDispatcher(store)  # لا تسجيل لأيّ معالِج

    res = asyncio.run(disp.dispatch(_cmd("cmd-1", command_type="unknown.type")))

    assert res.status == CommandStatus.FAILED
    assert res.error and "no handler" in res.error
    assert "unknown.type" in res.error
    assert res.result is None
    assert store._rows["cmd-1"]["status"] == CommandStatus.FAILED  # عُلِّم failed فعلاً
    assert store._rows["cmd-1"]["retry_count"] == 1  # mark_failed زاد العدّاد


# ─── register / registered_types ─────────────────────────────────


def test_register_duplicate_type_raises_value_error():
    """تسجيل نوع مكرّر يرفع ValueError."""
    store = FakeStore()
    disp = CommandDispatcher(store)
    disp.register("t", _ok_handler(store))

    with pytest.raises(ValueError, match="already registered"):
        disp.register("t", _ok_handler(store))


def test_registered_types_returns_sorted_registered():
    """registered_types يُرجِع الأنواع المسجّلة مرتّبة."""
    store = FakeStore()
    disp = CommandDispatcher(store)
    assert disp.registered_types() == []

    disp.register("zeta", _ok_handler(store))
    disp.register("alpha", _ok_handler(store))

    assert disp.registered_types() == ["alpha", "zeta"]


# ─── حقول DispatchResult في المسار الناجح ────────────────────────


def test_dispatch_result_fields_on_success_path():
    """مسار جديد ناجح ⇒ DispatchResult بالحقول الصحيحة + الأمر succeeded."""
    store = FakeStore()
    disp = CommandDispatcher(store)
    payload = {"created": "yes"}
    disp.register("t", _ok_handler(store, payload=payload))

    res = asyncio.run(disp.dispatch(_cmd("cmd-new")))

    assert isinstance(res, DispatchResult)
    assert res.command_id == "cmd-new"
    assert res.status == CommandStatus.SUCCEEDED
    assert res.result == payload
    assert res.error is None
    assert res.was_duplicate is False  # تنفيذ أوّليّ لا تكرار
    assert store.exec_count == 1
    assert store._rows["cmd-new"]["status"] == CommandStatus.SUCCEEDED


def test_handler_exception_returns_failed_result():
    """رمي المعالِج استثناءً ⇒ DispatchResult.FAILED مع نوع الاستثناء + الأمر failed."""
    store = FakeStore()
    disp = CommandDispatcher(store)

    async def boom(cmd):
        store.exec_count += 1
        raise RuntimeError("kaboom")

    disp.register("t", boom)

    res = asyncio.run(disp.dispatch(_cmd("cmd-err")))

    assert res.status == CommandStatus.FAILED
    assert res.error and "RuntimeError" in res.error
    assert "kaboom" in res.error
    assert res.result is None
    assert res.was_duplicate is False
    assert store.exec_count == 1
    assert store._rows["cmd-err"]["status"] == CommandStatus.FAILED


def test_failed_command_below_max_retries_is_retried():
    """أمر FAILED تحت MAX_RETRIES يُعاد التقاطه وتنفيذه بنجاح."""
    store = FakeStore()
    store.seed("cmd-r", CommandStatus.FAILED, error="prev", retry_count=1)
    disp = CommandDispatcher(store)
    disp.register("t", _ok_handler(store, payload={"recovered": True}))

    res = asyncio.run(disp.dispatch(_cmd("cmd-r")))

    assert res.status == CommandStatus.SUCCEEDED
    assert res.result == {"recovered": True}
    assert res.was_duplicate is False
    assert store.exec_count == 1
    assert store._rows["cmd-r"]["status"] == CommandStatus.SUCCEEDED


# ─── Command.new ─────────────────────────────────────────────────


def test_command_new_generates_valid_defaults():
    """Command.new يولّد command_id (UUID) وحالة PENDING ومصدراً افتراضيّاً MOBILE."""
    cmd = Command.new(
        command_type="field.create",
        actor_id="actor-1",
        tenant_id="tenant-1",
        payload={"name": "n"},
    )

    assert cmd.command_type == "field.create"
    assert cmd.actor_id == "actor-1"
    assert cmd.tenant_id == "tenant-1"
    assert cmd.payload == {"name": "n"}
    assert cmd.status == CommandStatus.PENDING
    assert cmd.source == CommandSource.MOBILE
    assert cmd.retry_count == 0
    assert cmd.result is None
    assert cmd.error is None
    # command_id افتراضيّ ⇒ UUID صالح
    import uuid

    assert uuid.UUID(cmd.command_id)


def test_command_new_respects_explicit_id_and_source():
    """Command.new يحترم command_id ومصدراً صريحَين."""
    cmd = Command.new(
        command_type="t",
        actor_id="a",
        tenant_id="te",
        payload={},
        source=CommandSource.WEB,
        command_id="explicit-id",
    )

    assert cmd.command_id == "explicit-id"
    assert cmd.source == CommandSource.WEB


def test_command_new_unique_ids():
    """أمران بلا command_id صريح ⇒ معرّفان مختلفان."""
    a = Command.new(command_type="t", actor_id="a", tenant_id="te", payload={})
    b = Command.new(command_type="t", actor_id="a", tenant_id="te", payload={})
    assert a.command_id != b.command_id


if __name__ == "__main__":
    import inspect

    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            fn()
    print("✓ كل اختبارات سلوك command store (v66) نجحت")
