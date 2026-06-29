"""Rate-limit middleware on the platform API (CI-enforced).

الفجوة المسدودة (تدقيق التغطية، الأمن): النواة (platform API) كانت بلا أيّ حدّ
معدّل ⇒ مكشوفة لـbrute-force/DoS. هذه الاختبارات تُثبِت أنّ الحاجز يعمل عبر HTTP
(يحجب بعد الحدّ بـ429) وأنّ نقاط الصحّة مُعفاة (لا تُحجب أبداً).
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def app_mod():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m

    return m


@pytest.mark.integration
def test_rate_limit_blocks_over_limit(app_mod, monkeypatch):
    from fastapi.testclient import TestClient

    m = app_mod
    monkeypatch.setattr(m, "_RATE_LIMIT_PER_MIN", 3)
    monkeypatch.setattr(
        m, "_RATE_REDIS", None
    )  # يفرض المسار in-process (حتميّ بصرف النظر عن البيئة)
    m._rate_buckets.clear()
    try:
        client = TestClient(m.app)
        # أوّل ٣ طلبات تمرّ (قد تكون 401/404، لكن ليست 429)
        for _ in range(3):
            r = client.get("/api/v1/fields")
            assert r.status_code != 429, r.status_code
        # الطلب الرابع يتجاوز الحدّ ⇒ 429 مع Retry-After
        r = client.get("/api/v1/fields")
        assert r.status_code == 429, r.text
        assert "Retry-After" in r.headers
        assert "طلبات كثيرة" in r.text
    finally:
        m._rate_buckets.clear()


@pytest.mark.integration
def test_rate_limit_exempts_health(app_mod, monkeypatch):
    from fastapi.testclient import TestClient

    m = app_mod
    monkeypatch.setattr(m, "_RATE_LIMIT_PER_MIN", 2)
    monkeypatch.setattr(m, "_RATE_REDIS", None)  # يفرض المسار in-process (حتميّ)
    m._rate_buckets.clear()
    try:
        client = TestClient(m.app)
        # نقاط الصحّة مُعفاة — تتجاوز الحدّ بلا 429 (للـliveness/readiness probes)
        for _ in range(6):
            r = client.get("/healthz")
            assert r.status_code != 429, r.status_code
    finally:
        m._rate_buckets.clear()


@pytest.mark.unit
def test_rate_limit_disabled_when_zero(app_mod, monkeypatch):
    """حدّ ≤ 0 يعطّل الحاجز (مخرج هروب للبيئات الخاصّة) — لا حجب إطلاقاً."""
    from fastapi.testclient import TestClient

    m = app_mod
    monkeypatch.setattr(m, "_RATE_LIMIT_PER_MIN", 0)
    monkeypatch.setattr(m, "_RATE_REDIS", None)
    m._rate_buckets.clear()
    try:
        client = TestClient(m.app)
        for _ in range(10):
            r = client.get("/api/v1/fields")
            assert r.status_code != 429
    finally:
        m._rate_buckets.clear()


class _FakeRedis:
    """عميل Redis أدنى لاختبار منطق العدّ المشترَك (INCR/EXPIRE/TTL) بلا خادم حقيقيّ."""

    def __init__(self, *, fail: bool = False):
        self._n: dict[str, int] = {}
        self._ttl: dict[str, int] = {}
        self._fail = fail

    def incr(self, k):
        if self._fail:
            raise RuntimeError("redis down")
        self._n[k] = self._n.get(k, 0) + 1
        return self._n[k]

    def expire(self, k, ttl):
        self._ttl[k] = ttl

    def ttl(self, k):
        return self._ttl.get(k, -1)


@pytest.mark.unit
def test_rate_check_redis_blocks_over_limit(app_mod, monkeypatch):
    """المسار المشترَك (Redis): يسمح حتّى الحدّ ثمّ يحجب مع retry_after موجب + EXPIRE مرّة."""
    m = app_mod
    fake = _FakeRedis()
    monkeypatch.setattr(m, "_RATE_REDIS", fake)
    monkeypatch.setattr(m, "_RATE_LIMIT_PER_MIN", 2)
    assert m._rate_check_redis("1.2.3.4") == (True, 0)  # 1
    assert m._rate_check_redis("1.2.3.4") == (True, 0)  # 2 (عند الحدّ)
    allowed, retry = m._rate_check_redis("1.2.3.4")  # 3 (تجاوز)
    assert allowed is False and retry >= 1
    assert fake._ttl.get("sahool:ratelimit:1.2.3.4") == 60  # EXPIRE ضُبط على أوّل ضربة
    # مفتاح مختلف لا يتأثّر (نافذة لكلّ عميل).
    assert m._rate_check_redis("9.9.9.9") == (True, 0)


@pytest.mark.unit
def test_rate_check_redis_fail_open(app_mod, monkeypatch):
    """عطل Redis ⇒ fail-open (True, 0) — لا يكسر مسار الطلب (حاجز DoS لا بوّابة أمن)."""
    m = app_mod
    monkeypatch.setattr(m, "_RATE_REDIS", _FakeRedis(fail=True))
    monkeypatch.setattr(m, "_RATE_LIMIT_PER_MIN", 1)
    assert m._rate_check_redis("1.2.3.4") == (True, 0)
