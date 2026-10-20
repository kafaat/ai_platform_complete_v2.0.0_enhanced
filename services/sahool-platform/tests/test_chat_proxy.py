"""Tests for api/chat_proxy_reference.py — the security gate protecting the Claude API key.
Verifies rate-limiting, token cap, and server-side context injection. Previously ZERO tests."""

import importlib.util
import sys
import time
from pathlib import Path

# تحميل الوحدة المرجعية (خارج core/، في api/)
_spec = importlib.util.spec_from_file_location(
    "chat_proxy", Path(__file__).parent.parent / "api" / "chat_proxy_reference.py"
)
proxy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proxy)


class TestRateLimit:
    def setup_method(self):
        proxy._calls.clear()  # عزل كل اختبار

    def test_allows_under_limit(self):
        assert proxy.check_rate_limit("farm_A") is True

    def test_blocks_over_limit(self):
        # 10 مسموحة، الـ11 تُرفَض
        for _ in range(proxy._RATE_LIMIT_PER_MIN):
            proxy.check_rate_limit("farm_B")
        assert proxy.check_rate_limit("farm_B") is False

    def test_tenants_isolated(self):
        # استنزاف مزرعة لا يؤثّر على أخرى
        for _ in range(proxy._RATE_LIMIT_PER_MIN):
            proxy.check_rate_limit("farm_C")
        assert proxy.check_rate_limit("farm_D") is True


class TestProxyRequest:
    def test_token_cap_enforced(self):
        # سقف وقائي: حتى لو طلبت الواجهة 99999، يُقصّ إلى 1024
        req = proxy.build_proxy_request({"max_tokens": 99999, "messages": []}, "ctx", "test-model")
        assert req["max_tokens"] <= 1024

    def test_context_from_server_not_client(self):
        # السياق يأتي من الخادم (farm_context)، لا مما ترسله الواجهة (صيغة Messages)
        req = proxy.build_proxy_request(
            {"system": "MALICIOUS", "messages": []}, "SERVER_CTX", "test-model"
        )
        assert req["system"] == "SERVER_CTX"

    def test_resolved_model_used(self):
        # النموذج يأتي مُحلولاً من تهيئة المزوّد (البيئة)، لا قيمة مضمّنة في الكود.
        req = proxy.build_proxy_request({"messages": []}, "ctx", "deepseek/deepseek-chat")
        assert req["model"] == "deepseek/deepseek-chat"

    def test_openai_chat_wire_format_injects_system_message(self):
        # OpenRouter (openai_chat): السياق الخادميّ يُحقن كرسالة system في المقدّمة.
        req = proxy.build_proxy_request(
            {"messages": [{"role": "user", "content": "hi"}]},
            "SERVER_CTX",
            "deepseek/deepseek-chat",
            "openai_chat",
        )
        assert "system" not in req  # لا حقل system منفصل في صيغة OpenAI
        assert req["messages"][0] == {"role": "system", "content": "SERVER_CTX"}
        assert req["messages"][-1]["content"] == "hi"


class TestProviderPreferencesOnTheWire:
    """مسار ``POST /api/chat`` المرجعيّ: ما يُرسَل فعلاً إلى OpenRouter يحمل تفضيلات
    الخصوصيّة (``data_collection=deny`` و``zdr=true``)، ولا تستطيع الواجهة إرخاءها."""

    def _post(self, monkeypatch, provider):
        import pytest

        pytest.importorskip("fastapi")
        from types import SimpleNamespace

        assert proxy.app is not None, "تطبيق المرجع لم يُبنَ رغم توفّر FastAPI"

        from fastapi.testclient import TestClient

        for key in ("AI_MODEL", "AI_MODELS", "OPENROUTER_BASE_URL", "OLLAMA_BASE_URL"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("AI_PROVIDER", provider)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        sent = []

        class _Upstream:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, headers=None, json=None):
                sent.append(json)
                return SimpleNamespace(json=lambda: {"ok": True})

        monkeypatch.setattr(proxy, "httpx", SimpleNamespace(AsyncClient=_Upstream))
        monkeypatch.setattr(proxy, "_tenant_from_jwt", lambda request: "farm_wire")
        proxy._calls.clear()
        body = {
            "messages": [{"role": "user", "content": "hi"}],
            "provider": {"data_collection": "allow", "zdr": False},
        }
        resp = TestClient(proxy.app).post("/api/chat", json=body)
        assert resp.status_code == 200
        assert len(sent) == 1
        return sent[0]

    def test_openrouter_request_carries_privacy_preferences(self, monkeypatch):
        payload = self._post(monkeypatch, "openrouter")
        assert payload["provider"] == {"data_collection": "deny", "zdr": True}

    def test_local_request_carries_no_provider_preferences(self, monkeypatch):
        payload = self._post(monkeypatch, "local")
        assert "provider" not in payload
