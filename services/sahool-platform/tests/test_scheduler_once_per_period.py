"""R7 — ``cluster_singleton`` يُشغّل المهمّة **مرّة لكلّ فترة** عبر العنقود، لا مرّة لكلّ نسخة.

القفل الاستشاريّ يمنع التداخل فقط: N نسخة بأطوار مختلفة كانت تُشغّل المهمّة اليوميّة
N مرّة متتابعة. الإصلاح يحجز الفترة في Redis (SET NX PX). الاختبار نقيّ: الوصلتان
(القفل الاستشاريّ وعميل Redis) تُرقَّعان كدوالّ — بلا اتّصال قاعدة وهميّ — ومخزن TTL
بساعة مُتحكَّم بها يحاكي Redis.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from api import scheduler as sched
from api.scheduler import Scheduler, cluster_singleton

pytestmark = pytest.mark.unit

PERIOD = 100.0


class _TtlStore:
    """محاكاة Redis الدنيا: ``SET [NX] PX`` و``EVAL`` الحذف الشرطيّ، بساعة يدويّة."""

    def __init__(self) -> None:
        self.now = 0.0
        self.data: dict[str, tuple[str, float]] = {}
        self.fail = False

    def _live(self, key: str) -> str | None:
        item = self.data.get(key)
        if item is None or item[1] <= self.now:
            self.data.pop(key, None)
            return None
        return item[0]

    def set(self, key, value, nx=False, px=None):  # noqa: A003 — توقيع redis-py
        if self.fail:
            raise ConnectionError("redis down")
        if nx and self._live(key) is not None:
            return None
        self.data[key] = (value, self.now + px / 1000.0)
        return True

    def eval(self, script, numkeys, key, token):  # noqa: A003 — توقيع redis-py
        if self._live(key) == token:
            del self.data[key]
            return 1
        return 0


@pytest.fixture
def store(monkeypatch):
    s = _TtlStore()
    monkeypatch.setattr(sched, "_period_redis", lambda: s)

    @asynccontextmanager
    async def _always_locked(pool, key):  # كلّ تكّة هنا متسلسلة ⇒ القفل متاح دائماً
        yield True

    monkeypatch.setattr(sched, "_advisory_session_lock", _always_locked)
    return s


def _replicas(n: int, calls: list[str], *, fail_first: bool = False):
    """N نسخة مستقلّة (كلّ واحدة مُجدوِلها ولفّها) لنفس المهمّة، مُسجَّلة بفاصل PERIOD."""
    out = []
    state = {"failed": not fail_first}
    for i in range(n):
        name = f"replica-{i}"

        async def _task(name=name):
            if not state["failed"]:
                state["failed"] = True
                raise RuntimeError("provider down")
            calls.append(name)

        wrapped = cluster_singleton(_task, task_name="fetch_weather", pool_getter=lambda: object())
        Scheduler().register("fetch_weather", PERIOD, wrapped)  # يربط الفترة بالفاصل
        out.append(wrapped)
    return out


def test_n_replicas_run_once_per_period_not_n_times(store):
    calls: list[str] = []
    replicas = _replicas(3, calls)
    # ثلاث نسخ بأطوار 0/10/20ث، كلٌّ يتكّ كلّ PERIOD، على ثلاث فترات.
    ticks = sorted((k * PERIOD + phase, i) for k in range(3) for i, phase in enumerate((0, 10, 20)))
    for at, i in ticks:
        store.now = at
        asyncio.run(replicas[i]())
    assert len(calls) == 3, calls  # مرّة لكلّ فترة — كانت 9 (3 نسخ × 3 فترات)


def test_single_replica_behaviour_unchanged(store):
    calls: list[str] = []
    (only,) = _replicas(1, calls)
    # التكّة التالية تأتي بعد PERIOD كاملة من نهاية التشغيل (حلقة Scheduler) ⇒ تعمل كلّها.
    for k in range(5):
        store.now = k * (PERIOD + 0.001)
        asyncio.run(only())
    assert len(calls) == 5


def test_failed_run_releases_the_period_for_a_retry(store):
    calls: list[str] = []
    a, b = _replicas(2, calls, fail_first=True)
    with pytest.raises(RuntimeError):
        asyncio.run(a())  # فشل ⇒ لا تُسجَّل الفترة
    store.now = 10
    asyncio.run(b())
    assert calls == ["replica-1"]  # نسخة أخرى تُعيد المحاولة في الفترة نفسها


def test_redis_outage_fails_open_to_lock_only(store):
    calls: list[str] = []
    a, b = _replicas(2, calls)
    store.fail = True
    asyncio.run(a())
    asyncio.run(b())
    assert calls == ["replica-0", "replica-1"]  # عطل Redis لا يُجمّد المهامّ


def test_without_redis_url_no_period_store(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert sched._period_redis() is None


def test_period_ttl_never_exceeds_the_interval():
    assert sched._period_ttl_ms(15) < 15_000
    assert sched._period_ttl_ms(86400) == (86400 - 30) * 1000
