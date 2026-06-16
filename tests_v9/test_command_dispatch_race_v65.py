"""
tests_v9/test_command_dispatch_race_v65.py — يُثبت إصلاح سباق التقاط الأمر.

Pure logic (مخزن وهميّ في الذاكرة) — لا DB. يتحقّق من:
  ① إعادة أمر FAILED لا تدخل تكراراً لا نهائيّاً (كان `return dispatch()` يكرّر
     بلا تغيّر حالة ⇒ stack overflow).
  ② الالتقاط الذرّيّ (mark_processing بحارس الحالة) يمنع التنفيذ المزدوج:
     عاملان على نفس الأمر ⇒ معالِجٌ يُنفَّذ مرّةً واحدة فقط.
  ③ تجاوز MAX_RETRIES ⇒ فشل نهائيّ (dead-letter) لا إعادة لا نهائيّة.
"""

import asyncio
import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))


class FakeStore:
    """مخزن أوامر وهميّ يحاكي حارس الحالة الذرّيّ في mark_processing."""

    def __init__(self, seed=None):
        self._rows = dict(seed or {})  # command_id -> status
        self.exec_count = 0

    async def get(self, cid):
        from api.command_store import Command, CommandSource, CommandStatus

        st = self._rows.get(cid)
        if st is None:
            return None
        return Command(
            command_id=cid,
            command_type="t",
            actor_id="a",
            tenant_id=None,
            payload={},
            source=CommandSource.SCHEDULER,
            status=CommandStatus(st),
            retry_count=0,
        )

    async def insert(self, cmd):
        if cmd.command_id in self._rows:
            return False
        self._rows[cmd.command_id] = "pending"
        return True

    async def mark_processing(self, cid):
        # الحارس الذرّيّ: pending|failed → processing فقط. غيرهما → False.
        if self._rows.get(cid) in ("pending", "failed"):
            self._rows[cid] = "processing"
            return True
        return False

    async def mark_succeeded(self, cid, result):
        self._rows[cid] = "succeeded"

    async def mark_failed(self, cid, error):
        self._rows[cid] = "failed"


def _make_cmd(cid, status_seed):
    from api.command_store import Command, CommandSource, CommandStatus

    return Command(
        command_id=cid,
        command_type="t",
        actor_id="a",
        tenant_id=None,
        payload={},
        source=CommandSource.SCHEDULER,
        status=CommandStatus(status_seed),
        retry_count=0,
    )


def test_failed_retry_no_infinite_loop():
    """إعادة أمر FAILED تُنفَّذ مرّةً (لا تكرار لا نهائيّ)."""
    from api.command_store import CommandDispatcher, CommandStatus

    store = FakeStore(seed={"c1": "failed"})
    disp = CommandDispatcher(store)

    async def handler(cmd):
        store.exec_count += 1
        return {"ok": True}

    disp.register("t", handler)
    res = asyncio.run(disp.dispatch(_make_cmd("c1", "failed")))

    assert res.status == CommandStatus.SUCCEEDED
    assert store.exec_count == 1  # نُفِّذ مرّةً لا حلقة
    assert store._rows["c1"] == "succeeded"


def test_concurrent_dispatch_executes_once():
    """عاملان على نفس الأمر الجديد ⇒ تنفيذ واحد فقط (atomic claim)."""
    from api.command_store import CommandDispatcher

    store = FakeStore()
    disp = CommandDispatcher(store)

    async def handler(cmd):
        store.exec_count += 1
        await asyncio.sleep(0)  # يتيح للعامل الآخر التداخل
        return {"ok": True}

    disp.register("t", handler)

    async def run_both():
        c = _make_cmd("c2", "pending")
        return await asyncio.gather(disp.dispatch(c), disp.dispatch(c))

    results = asyncio.run(run_both())
    # معالِج نُفِّذ مرّةً واحدة فقط رغم عاملين.
    assert store.exec_count == 1, f"تنفيذ مزدوج! exec_count={store.exec_count}"
    statuses = {r.status.value for r in results}
    assert "succeeded" in statuses or "processing" in statuses


def test_max_retries_dead_letter():
    """أمر يتجاوز MAX_RETRIES لا يُعاد بل يُرجَع فشلاً نهائيّاً."""
    from api.command_store import Command, CommandDispatcher, CommandSource, CommandStatus

    store = FakeStore()
    # نبني أمراً موجوداً بحالة failed و retry_count مرتفع.
    cid = "c_dl"
    store._rows[cid] = "failed"
    disp = CommandDispatcher(store)

    # نُلبِس get لإرجاع retry_count فوق الحدّ.
    async def get_high_retry(_cid):
        return Command(
            command_id=cid,
            command_type="t",
            actor_id="a",
            tenant_id=None,
            payload={},
            source=CommandSource.SCHEDULER,
            status=CommandStatus.FAILED,
            retry_count=CommandDispatcher.MAX_RETRIES,
        )

    store.get = get_high_retry

    async def handler(cmd):
        store.exec_count += 1
        return {}

    disp.register("t", handler)

    res = asyncio.run(disp.dispatch(_make_cmd(cid, "failed")))
    assert res.status == CommandStatus.FAILED
    assert store.exec_count == 0  # لم يُنفَّذ — تجاوز الحدّ
    assert "max_retries" in (res.error or "")


if __name__ == "__main__":
    test_failed_retry_no_infinite_loop()
    test_concurrent_dispatch_executes_once()
    test_max_retries_dead_letter()
    print("✓ كل اختبارات سباق إرسال الأوامر (v65) نجحت")
