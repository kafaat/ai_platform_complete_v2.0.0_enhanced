from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

from shared.security.service_tenant_assertion import verify_tenant_assertion

MODULE = Path(__file__).with_name("vegetation_runtime.py")
spec = importlib.util.spec_from_file_location("vegetation_runtime_catalog_test", MODULE)
vr = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(vr)


_ASSERTION_KEY = "k" * 32
_ASSERTION_KEY_ID = "test-kid"


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
        # The owner verifies a request-bound signed tenant assertion, not the bare
        # X-Tenant-Id header: it must verify for this caller, tenant, method and path.
        verify_tenant_assertion(
            headers["X-Tenant-Assertion"],
            {_ASSERTION_KEY_ID: _ASSERTION_KEY},
            "vegetation-analysis-service",
            "tenant-a",
            expected_method="GET",
            expected_path="/internal/fields",
            expected_request_id=headers["X-Request-Id"],
        )
        return _Response()


def _configure(monkeypatch, *, assertion_key: str = _ASSERTION_KEY) -> None:
    monkeypatch.setattr(vr, "FIELD_SERVICE_URL", "http://field-management:8000")
    monkeypatch.setattr(vr, "RASTER_SERVICE_TOKEN", "service-token")
    monkeypatch.setattr(vr, "FIELD_SERVICE_TENANT_ASSERTION_KEY", assertion_key)
    monkeypatch.setattr(vr, "FIELD_SERVICE_TENANT_ASSERTION_KEY_ID", _ASSERTION_KEY_ID)
    monkeypatch.setattr(vr.httpx, "AsyncClient", _Client)


@pytest.mark.asyncio
async def test_platform_catalog_is_tenant_scoped_and_authenticated(monkeypatch):
    _configure(monkeypatch)
    assert await vr.list_fields_from_platform("tenant-a") == [{"id": "f-1", "name": "Field 1"}]


@pytest.mark.asyncio
async def test_platform_catalog_fails_closed_without_tenant_assertion_key(monkeypatch):
    _configure(monkeypatch, assertion_key="")
    with pytest.raises(HTTPException) as exc:
        await vr.list_fields_from_platform("tenant-a")
    assert exc.value.status_code == 503
    assert exc.value.detail == "field_tenant_assertion_unavailable"


def test_runtime_registry_is_empty_and_legacy_default_is_off():
    assert vr.FIELD_REGISTRY == {}
    assert vr.ALLOW_LEGACY_FIELD_REGISTRY is False
