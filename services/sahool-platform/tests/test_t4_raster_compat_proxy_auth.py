"""T4 (audit 2026-11-01): ``/api/raster/{path:path}`` must not be an anonymous service-token proxy.

Before the fix the compat route was unauthenticated and ``raster_get_raw`` attached
``X-Agent-Token`` (the raster service token) to whatever path/tenant the caller chose,
so an anonymous request reached service-only raster routes (offline packs, storage
stats, jobs). These tests pin the nginx ``/api/raster/`` contract on the platform
fallback: JWT required, tenant from the token, no service token, explicit allowlist.
"""

from __future__ import annotations

import httpx
import pytest
from api.main import get_current_user
from api.routers import compat_gateway
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_TENANT = "00000000-0000-0000-0000-0000000000a1"
_SERVICE_TOKEN = "svc-secret-must-not-leak"


def _user() -> UserSchema:
    return UserSchema(user_id="u-1", tenant_id=_TENANT, role=UserRole.VIEWER, name_ar="مستخدم")


@pytest.fixture
def upstream(monkeypatch):
    """Capture every request the platform sends to raster-service (wire level)."""
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _SERVICE_TOKEN)
    monkeypatch.setenv("RASTER_SERVICE_URL", "http://raster.test")
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True}, headers={"cache-control": "no-store"})

    real_async_client = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client)
    return seen


def _client(*, authenticated: bool) -> TestClient:
    app = FastAPI()
    app.include_router(compat_gateway.router)
    if authenticated:
        app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    [
        "/api/raster/v1/offline/packs",
        "/api/raster/v1/storage/stats",
        "/api/raster/v1/fields/f1/tilejson?tid=" + _TENANT,
    ],
)
def test_anonymous_request_is_401_and_never_reaches_raster(upstream, path):
    r = _client(authenticated=False).get(path)
    assert r.status_code == 401
    assert upstream == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/raster/v1/offline/packs",
        "/api/raster/v1/offline/packs/pack.mbtiles",
        "/api/raster/v1/storage/stats",
        "/api/raster/v1/jobs/job-1/result",
        "/api/raster/v1/info/layer-1",
        "/api/raster/v1/fields/f1/indicator-observation-bundle",
        "/api/raster/v1/fields/f1/tilejson/extra",  # full match, not prefix/substring
        "/api/raster/xv1/fields/f1/tilejson",
    ],
)
def test_authenticated_non_allowlisted_path_is_404_without_upstream_call(upstream, path):
    r = _client(authenticated=True).get(path, headers={"Authorization": "Bearer user-jwt"})
    assert r.status_code == 404
    assert upstream == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/raster/v1/fields/%2e%2e/offline/packs",
        "/api/raster/v1/fields/f1/%2e%2e/%2e%2e/offline/packs",
        "/api/raster/v1/fields/%252e%252e/tilejson",
        "/api/raster/v1/fields/f1%2ftilejson",
        "/api/raster/v1/fields/f1%5ctilejson",
        "/api/raster//v1/fields/f1/tilejson",
    ],
)
def test_encoded_traversal_is_rejected_without_upstream_call(upstream, path):
    r = _client(authenticated=True).get(path, headers={"Authorization": "Bearer user-jwt"})
    assert r.status_code == 404
    assert upstream == []


@pytest.mark.parametrize(
    "path",
    [
        "v1/fields/../offline/packs",
        "v1/fields/f1/../../storage/stats",
        "v1/fields/./tilejson",
        "v1/fields/%2e%2e/tilejson",
        "v1/fields/f1\\..\\tilejson",
        "v1/fields/f1/tilejson\n",
        "",
    ],
)
def test_path_matcher_rejects_raw_traversal(path):
    assert compat_gateway._raster_compat_path_allowed(path) is False


def test_allowlisted_read_forwards_user_auth_and_token_tenant_but_no_service_token(upstream):
    r = _client(authenticated=True).get(
        "/api/raster/v1/fields/fld_1/tilejson",
        params={"index": "ndvi", "tid": "evil-tenant", "tenant_id": "evil", "access_token": "x"},
        headers={"Authorization": "Bearer user-jwt", "X-Tenant-Id": "evil-tenant"},
    )
    assert r.status_code == 200
    assert len(upstream) == 1
    sent = upstream[0]
    assert sent.method == "GET"
    assert sent.url.path == "/v1/fields/fld_1/tilejson"
    assert "x-agent-token" not in {k.lower() for k in sent.headers}
    assert _SERVICE_TOKEN not in str(sent.headers)
    assert sent.headers["X-Tenant-Id"] == _TENANT
    assert sent.headers["Authorization"] == "Bearer user-jwt"
    assert dict(sent.url.params) == {"index": "ndvi"}


@pytest.mark.parametrize(
    "path",
    [
        "v1/fields/fld_1/tiles/14/9000/7000.png",
        "v1/fields/fld_1/cdse-tiles/14/9000/7000.png",
        "v1/fields/fld_1/cdse-thumbnail.png",
        "v1/fields/fld_1/cdse-tilejson",
        "v1/fields/fld_1/indicator-grid",
        "v1/fields/fld_1/timeseries",
        "v1/fields/fld_1/contours.geojson",
        "v1/fields/fld_1/soil/sampling-plan",
        "v1/elevation/hillshade/10/1/2.png",
        "v1/slope/10/1/2.png",
        "v1/terrain/tilejson",
        "v1/soil/tilejson",
        "v1/soil/tiles/phh2o/0-5cm/10/1/2.png",
        "v1/soil/properties",
        "v1/imagery/backfill/policy",
    ],
)
def test_browser_and_mobile_read_paths_stay_allowlisted(path):
    assert compat_gateway._raster_compat_path_allowed(path) is True


def test_raster_get_raw_never_sends_service_token(upstream):
    import asyncio

    from api.raster_service_client import raster_get_raw

    asyncio.run(raster_get_raw("v1/terrain/tilejson", tenant_id=_TENANT))
    assert len(upstream) == 1
    assert "x-agent-token" not in {k.lower() for k in upstream[0].headers}
