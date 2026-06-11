#!/usr/bin/env python3
"""
اختبار التدهور اللطيف: عند فتح قاطع خدمة MCP، يجب أن يردّ /agent/query بـ200
مُوسَّماً `degraded` بدل 500 قاسٍ — المنصّة تبقى مستجيبة والقاطع يتعافى تلقائيّاً.

يعمل offline: يتجاوز المصادقة بـdependency_override، ويحقن مهارة تُحاكي قاطعاً
مفتوحاً عبر CircuitOpenError. يحتاج repo root + دليل الخدمة على المسار (CI/conftest).
"""

import os
import sys

# تمهيد المسار: main يستورد shared.* (جذر المستودع) إضافةً إلى وحدات الخدمة
# المسطّحة (circuit_breaker/router). نضمن توفّر الاثنين أيّاً كان مُشغّل pytest.
_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
for _p in (_REPO_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import main  # noqa: E402
from circuit_breaker import CircuitOpenError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _client_with_open_circuit(monkeypatch) -> TestClient:
    async def fake_classify(_query: str):
        return ("crop_model", "simulate_current", 0.9)

    class _OpenCircuitSkill:
        async def execute(self, **_kwargs):
            raise CircuitOpenError("weather متعطّلة (القاطع مفتوح) — تخطٍّ سريع")

    monkeypatch.setattr(main.router, "classify_intent", fake_classify)
    monkeypatch.setitem(main.skill_libraries, "crop_model", _OpenCircuitSkill())
    main.app.dependency_overrides[main._get_current_user] = lambda: {
        "sub": "u1",
        "tenant_id": "t1",
    }
    return TestClient(main.app)


def test_circuit_open_returns_graceful_degraded(monkeypatch):
    client = _client_with_open_circuit(monkeypatch)
    try:
        resp = client.post(
            "/agent/query",
            json={"query": "محاكاة المحصول", "user_id": "u1", "tenant_id": "t1"},
        )
    finally:
        main.app.dependency_overrides.clear()

    # تدهور لطيف: 200 لا 500
    assert resp.status_code == 200
    body = resp.json()
    assert body["structured_data"]["status"] == "degraded"
    assert body["structured_data"]["reason"] == "circuit_open"
    assert body["confidence"] == 0.0
    assert body["sources"] == []
    # رسالة عربيّة مفهومة للمزارع لا أثر استثناء
    assert "مؤقّت" in body["response_ar"]
