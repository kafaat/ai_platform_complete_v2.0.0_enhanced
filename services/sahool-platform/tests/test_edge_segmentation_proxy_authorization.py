"""The edge and segmentation BFF routes must authorise before attaching X-Agent-Token.

Both proxies used to accept any authenticated user for any method/path: a viewer
could flush the shared edge sync queue or push inference results under another
tenant's field_id. The real router, RBAC and dependency graph are exercised; only
the upstream client and the tenant connection are replaced.
"""

from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager

import httpx
import pytest
from api import main as platform
from api.main import get_current_user
from api.routers import service_proxy
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI

pytestmark = pytest.mark.unit

TENANT = "11111111-1111-4111-8111-111111111111"
OWN_FIELD = "field-own"
FOREIGN_FIELD = "field-of-another-tenant"


def _multipart(field_ids):
    boundary = "sahoolboundary"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="field_id"\r\n\r\n{fid}\r\n'
        for fid in field_ids
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.jpg"\r\n'
        "Content-Type: image/jpeg\r\n\r\nJPEGDATA\r\n"
    )
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts).encode(), f"multipart/form-data; boundary={boundary}"


def request_as(monkeypatch, role, method, url, *, field_ids=None, json=None):
    forwarded = []
    checked = []
    user = UserSchema(user_id="actor", tenant_id=TENANT, role=role, name_ar="t", is_active=True)
    app = FastAPI()
    app.include_router(service_proxy.router)

    async def identity():
        return user

    monkeypatch.setitem(app.dependency_overrides, get_current_user, identity)
    monkeypatch.setattr(platform, "_RATE_LIMIT_PER_MIN", 0)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", secrets.token_hex(20))

    class Conn:
        async def fetchval(self, _sql, field_id):
            checked.append(field_id)
            return 1 if field_id == OWN_FIELD else None

    @asynccontextmanager
    async def fake_tenant_connection(u):
        assert str(u.tenant_id) == TENANT
        yield Conn()

    monkeypatch.setattr(service_proxy, "tenant_connection", fake_tenant_connection, raising=False)

    class Upstream:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            req = httpx.Request(method, url, **kwargs)
            forwarded.append(req)
            return httpx.Response(200, json={"accepted": True})

    monkeypatch.setattr(service_proxy.httpx, "AsyncClient", Upstream)

    async def run():
        kwargs = {}
        if field_ids is not None:
            body, ctype = _multipart(field_ids)
            kwargs = {"content": body, "headers": {"Content-Type": ctype}}
        elif json is not None:
            kwargs = {"json": json}
        req = httpx.Request(method, "http://test.local" + url, **kwargs)
        return await httpx.ASGITransport(app=app).handle_async_request(req)

    return asyncio.run(run()), forwarded, checked


@pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.MANAGER, UserRole.VIEWER])
@pytest.mark.parametrize("method", ["POST", "GET"])
def test_nobody_can_trigger_the_shared_edge_sync_through_the_bff(monkeypatch, role, method):
    response, forwarded, _ = request_as(monkeypatch, role, method, "/api/edge/v1/sync/trigger")
    assert response.status_code == 404
    assert forwarded == []


@pytest.mark.parametrize("path", ["metrics", "internal/x", "v1/inference/../sync/trigger"])
def test_unlisted_edge_paths_never_receive_a_service_token(monkeypatch, path):
    response, forwarded, _ = request_as(monkeypatch, UserRole.OWNER, "POST", "/api/edge/" + path)
    assert response.status_code in {404, 405}
    assert forwarded == []


@pytest.mark.parametrize("route", ["pest-detect", "yield-estimate"])
def test_viewer_cannot_push_edge_inference_results(monkeypatch, route):
    response, forwarded, _ = request_as(
        monkeypatch,
        UserRole.VIEWER,
        "POST",
        f"/api/edge/v1/inference/{route}",
        field_ids=[OWN_FIELD],
    )
    assert response.status_code == 403
    assert forwarded == []


@pytest.mark.parametrize("route", ["pest-detect", "yield-estimate"])
def test_edge_inference_refuses_a_field_outside_the_callers_tenant(monkeypatch, route):
    response, forwarded, checked = request_as(
        monkeypatch,
        UserRole.WORKER,
        "POST",
        f"/api/edge/v1/inference/{route}",
        field_ids=[FOREIGN_FIELD],
    )
    assert response.status_code == 404
    assert checked == [FOREIGN_FIELD]
    assert forwarded == []


def test_edge_inference_refuses_ambiguous_or_missing_field_id(monkeypatch):
    for ids in ([], [OWN_FIELD, FOREIGN_FIELD]):
        response, forwarded, _ = request_as(
            monkeypatch,
            UserRole.OWNER,
            "POST",
            "/api/edge/v1/inference/pest-detect",
            field_ids=ids,
        )
        assert response.status_code == 422
        assert forwarded == []


@pytest.mark.parametrize("role", [UserRole.WORKER, UserRole.AGRONOMIST, UserRole.OWNER])
def test_mobile_pest_detect_on_an_owned_field_is_forwarded_intact(monkeypatch, role):
    response, forwarded, checked = request_as(
        monkeypatch,
        role,
        "POST",
        "/api/edge/v1/inference/pest-detect",
        field_ids=[OWN_FIELD],
    )
    assert response.status_code == 200
    assert checked == [OWN_FIELD]
    assert len(forwarded) == 1
    assert forwarded[0].url.path == "/v1/inference/pest-detect"
    assert forwarded[0].headers["X-Tenant-Id"] == TENANT
    assert b"JPEGDATA" in forwarded[0].content


def test_edge_capabilities_are_readable(monkeypatch):
    response, forwarded, _ = request_as(
        monkeypatch, UserRole.VIEWER, "GET", "/api/edge/capabilities"
    )
    assert response.status_code == 200
    assert len(forwarded) == 1


def test_viewer_cannot_run_segmentation(monkeypatch):
    response, forwarded, _ = request_as(
        monkeypatch, UserRole.VIEWER, "POST", "/api/segmentation/v1/segment", json={"mode": "auto"}
    )
    assert response.status_code == 403
    assert forwarded == []


def test_field_creator_can_run_the_frontend_segmentation_call(monkeypatch):
    response, forwarded, _ = request_as(
        monkeypatch, UserRole.MANAGER, "POST", "/api/segmentation/v1/segment", json={"mode": "auto"}
    )
    assert response.status_code == 200
    assert len(forwarded) == 1
    assert forwarded[0].url.path == "/v1/segment"


@pytest.mark.parametrize(("method", "path"), [("POST", "admin"), ("DELETE", "v1/segment")])
def test_unlisted_segmentation_calls_never_receive_a_service_token(monkeypatch, method, path):
    response, forwarded, _ = request_as(
        monkeypatch, UserRole.OWNER, method, "/api/segmentation/" + path, json={}
    )
    assert response.status_code in {404, 405}
    assert forwarded == []
