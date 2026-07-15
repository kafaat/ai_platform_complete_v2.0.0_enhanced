from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).with_name("vegetation_runtime.py")
spec = importlib.util.spec_from_file_location("vegetation_runtime_catalog_test", MODULE)
vr = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(vr)


class _Response:
    status_code = 200

    def json(self):
        return {"fields": [{"id": "f-1", "name": "Field 1"}]}


class _Client:
    def __init__(self, *args, **kwargs):
        self.headers = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, headers=None):
        self.headers = headers
        # field-management-service owns the catalog now (not the platform).
        assert url.endswith("/internal/fields")
        assert headers["X-Tenant-Id"] == "tenant-a"
        assert headers["X-Agent-Token"] == "service-token"
        return _Response()


@pytest.mark.asyncio
async def test_platform_catalog_is_tenant_scoped_and_authenticated(monkeypatch):
    monkeypatch.setattr(vr, "FIELD_SERVICE_URL", "http://field-management:8000")
    monkeypatch.setattr(vr, "RASTER_SERVICE_TOKEN", "service-token")
    monkeypatch.setattr(vr.httpx, "AsyncClient", _Client)
    assert await vr.list_fields_from_platform("tenant-a") == [{"id": "f-1", "name": "Field 1"}]


def test_runtime_registry_is_empty_and_legacy_default_is_off():
    assert vr.FIELD_REGISTRY == {}
    assert vr.ALLOW_LEGACY_FIELD_REGISTRY is False
