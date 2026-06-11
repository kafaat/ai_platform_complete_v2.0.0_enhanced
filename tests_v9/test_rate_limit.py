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
    m._rate_buckets.clear()
    try:
        client = TestClient(m.app)
        for _ in range(10):
            r = client.get("/api/v1/fields")
            assert r.status_code != 429
    finally:
        m._rate_buckets.clear()
