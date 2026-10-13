"""Regression: tenant bearer tokens must not traverse environment proxies."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import urllib.request

import pytest

pytestmark = pytest.mark.unit
POLICY = Path(__file__).resolve().parents[1] / "services/tts-service/tts_tenant_policy.py"


def test_policy_fetch_disables_environment_proxy(monkeypatch):
    spec = importlib.util.spec_from_file_location("tts_policy_proxy_guard", POLICY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handlers = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, *_):
            return b'{"tenant_id":"tenant-a"}'

    class Opener:
        def open(self, request, timeout):
            assert request.get_header("Authorization") == "Bearer private-token"
            return Response()

    def fake_build_opener(*provided):
        handlers.extend(provided)
        return Opener()

    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted-proxy.invalid:8080")
    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    assert module._get_json("https://platform.internal/api/v1/me", "Bearer private-token") == {
        "tenant_id": "tenant-a"
    }
    proxy_handlers = [h for h in handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}
    assert any(isinstance(h, module._NoRedirect) for h in handlers)
