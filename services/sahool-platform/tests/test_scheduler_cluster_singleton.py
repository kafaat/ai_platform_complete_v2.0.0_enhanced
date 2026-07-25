"""قفل نسخة-واحدة للمُجدوِل (``scheduler.cluster_singleton``) — اختبار نقيّ (بلا قاعدة).

مع تعدّد نسخ المنصّة، المهمّة الدوريّة يجب أن تُشغّلها نسخة واحدة فقط لكلّ تكّة عبر
``pg_try_advisory_lock`` غير الحاجب. يؤكّد الاختبار السلوك بمسبح وهميّ:
  * بلا مسبح ⇒ تشغيل محلّيّ (نسخة واحدة، لا تنازع).
  * القفل مملوك ⇒ تُشغَّل المهمّة ثمّ يُحرَّر القفل (unlock).
  * القفل غير مملوك ⇒ لا تُشغَّل المهمّة ولا يُحرَّر قفل لم يُملَك.
"""

import asyncio

import pytest
from api.scheduler import cluster_singleton

pytestmark = pytest.mark.unit


class _FakeConn:
    def __init__(self, *, lock_granted: bool):
        self._granted = lock_granted
        self.executed: list[str] = []

    async def fetchval(self, sql, *args):
        assert "pg_try_advisory_lock" in sql
        return self._granted

    async def execute(self, sql, *args):
        self.executed.append(sql)


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


def _run(coro):
    return asyncio.run(coro)


def test_no_pool_runs_locally():
    calls = {"n": 0}

    async def _task():
        calls["n"] += 1

    wrapped = cluster_singleton(_task, task_name="t", pool_getter=lambda: None)
    _run(wrapped())
    assert calls["n"] == 1  # عمليّة واحدة ⇒ تعمل بلا قفل


def test_lock_granted_runs_then_unlocks():
    calls = {"n": 0}
    conn = _FakeConn(lock_granted=True)

    async def _task():
        calls["n"] += 1

    wrapped = cluster_singleton(_task, task_name="t", pool_getter=lambda: _FakePool(conn))
    _run(wrapped())
    assert calls["n"] == 1
    assert any("pg_advisory_unlock" in s for s in conn.executed)  # حُرِّر القفل


def test_lock_denied_skips_and_no_unlock():
    calls = {"n": 0}
    conn = _FakeConn(lock_granted=False)

    async def _task():
        calls["n"] += 1

    wrapped = cluster_singleton(_task, task_name="t", pool_getter=lambda: _FakePool(conn))
    _run(wrapped())
    assert calls["n"] == 0  # نسخة أخرى تحمل القفل ⇒ تُخطّى
    assert conn.executed == []  # لا تحرير لقفل لم يُملَك


def test_unlock_runs_even_if_task_raises():
    conn = _FakeConn(lock_granted=True)

    async def _task():
        raise RuntimeError("boom")

    wrapped = cluster_singleton(_task, task_name="t", pool_getter=lambda: _FakePool(conn))
    with pytest.raises(RuntimeError):
        _run(wrapped())
    assert any("pg_advisory_unlock" in s for s in conn.executed)  # يُحرَّر في finally
