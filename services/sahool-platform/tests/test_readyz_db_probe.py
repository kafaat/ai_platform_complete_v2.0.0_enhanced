"""MED-001 (شهادة P12): readyz يجب أن يفحص اعتماديّة القاعدة فعليّاً، لا النواة فقط.

كان readyz يستند إلى handle_readyz (فحص in-memory) فيُرجِع ready رغم سقوط Postgres
(إيجابيّة كاذبة توجّه المنظّم حركةً لنسخة معطوبة). db_probe_ok يُجري SELECT 1 فعليّاً.
"""

from __future__ import annotations

import pytest
from core.api_adapter import db_probe_ok

pytestmark = pytest.mark.unit


class _Conn:
    def __init__(self, fail: bool):
        self._fail = fail

    async def fetchval(self, _q):
        if self._fail:
            raise RuntimeError("connection refused")
        return 1


class _Acquire:
    def __init__(self, fail: bool):
        self._fail = fail

    async def __aenter__(self):
        return _Conn(self._fail)

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, fail: bool):
        self._fail = fail

    def acquire(self):
        return _Acquire(self._fail)


@pytest.mark.asyncio
async def test_db_down_is_not_ready():
    """مسبح قائم لكن الفحص يفشل (Postgres ساقط) ⇒ ليست جاهزة (لا إيجابيّة كاذبة)."""
    assert await db_probe_ok(_Pool(fail=True)) is False


@pytest.mark.asyncio
async def test_db_up_is_ready():
    assert await db_probe_ok(_Pool(fail=False)) is True


@pytest.mark.asyncio
async def test_no_pool_is_ready():
    """بلا قاعدة مقصود (pool=None) ⇒ جاهزة (endpoints القاعدة تُرجِع 503 صراحةً)."""
    assert await db_probe_ok(None) is True


def test_readyz_endpoint_awaits_db_probe():
    """حارس ثابت: نقطة readyz في المنصّة تستدعي db_probe_ok (لا فحص نواة فقط)."""
    import os

    base = os.path.join(os.path.dirname(__file__), "..", "api", "main.py")
    src = open(base, encoding="utf-8").read()
    assert "await db_probe_ok(_DB_POOL)" in src, "readyz لا يفحص القاعدة ⇒ إيجابيّة كاذبة"
