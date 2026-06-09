"""Tests for api/chat_proxy_reference.py — the security gate protecting the Claude API key.
Verifies rate-limiting, token cap, and server-side context injection. Previously ZERO tests."""
import sys, time, importlib.util
from pathlib import Path

# تحميل الوحدة المرجعية (خارج core/، في api/)
_spec = importlib.util.spec_from_file_location(
    "chat_proxy", Path(__file__).parent.parent / "api" / "chat_proxy_reference.py")
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
        req = proxy.build_proxy_request({"max_tokens": 99999, "messages": []}, "ctx")
        assert req["max_tokens"] <= 1024

    def test_context_from_server_not_client(self):
        # السياق يأتي من الخادم (farm_context)، لا مما ترسله الواجهة
        req = proxy.build_proxy_request({"system": "MALICIOUS", "messages": []}, "SERVER_CTX")
        assert req["system"] == "SERVER_CTX"

    def test_default_model_set(self):
        req = proxy.build_proxy_request({"messages": []}, "ctx")
        assert "claude" in req["model"]
