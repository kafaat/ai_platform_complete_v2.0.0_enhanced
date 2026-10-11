"""Exercise the real BFF router and RBAC before any service credential leaves it."""

from __future__ import annotations

import asyncio
import secrets

import httpx
import pytest
from api import main as platform
from api.main import get_current_user
from api.routers import service_proxy
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI

pytestmark = pytest.mark.unit

TENANT = "11111111-1111-4111-8111-111111111111"


def request_as(monkeypatch, role, method, path, *, active=True, full_platform=False):
    forwarded = []
    user = UserSchema(
        user_id="trusted-actor", tenant_id=TENANT, role=role, name_ar="test", is_active=active
    )
    app = platform.app if full_platform else FastAPI()
    if not full_platform:
        app.include_router(service_proxy.router)

    async def identity():
        return user

    monkeypatch.setitem(app.dependency_overrides, get_current_user, identity)
    monkeypatch.setattr(platform, "_RATE_LIMIT_PER_MIN", 0)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", secrets.token_hex(20))

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
        # Call ASGI directly so the upstream replacement cannot intercept this
        # test request. The router, dependency graph and RBAC are real.
        req = httpx.Request(
            method,
            "http://test.local/api/soil/" + path,
            headers={"X-Actor-Id": "spoofed", "X-Tenant-Id": "spoofed", "X-Agent-Token": "spoofed"},
        )
        return await httpx.ASGITransport(app=app).handle_async_request(req)

    return asyncio.run(run()), forwarded


@pytest.mark.parametrize(
    "path", ["v1/soil/ingest", "v1/soil/observations", "v1/fields/f1/soil/evidence"]
)
def test_viewer_cannot_turn_jwt_into_a_write_token(monkeypatch, path):
    response, forwarded = request_as(monkeypatch, UserRole.VIEWER, "POST", path)
    assert response.status_code == 403
    assert forwarded == []


@pytest.mark.parametrize("role", [UserRole.WORKER, UserRole.AGRONOMIST, UserRole.OWNER])
def test_observation_writers_are_allowed_and_client_identity_is_replaced(monkeypatch, role):
    response, forwarded = request_as(monkeypatch, role, "POST", "v1/soil/ingest")
    assert response.status_code == 200
    assert len(forwarded) == 1
    assert forwarded[0].headers["X-Tenant-Id"] == TENANT
    assert forwarded[0].headers["X-Actor-Id"] == "trusted-actor"
    assert forwarded[0].headers["X-Agent-Token"] != "spoofed"


@pytest.mark.parametrize(
    "path",
    [
        "v1/fields/f1/soil/profile",
        "v1/fields/f1/soil/closed-loop",
        "v1/fields/f1/soil/profile/history",
    ],
)
def test_existing_frontend_read_routes_remain_available_to_viewers(monkeypatch, path):
    response, forwarded = request_as(monkeypatch, UserRole.VIEWER, "GET", path)
    assert response.status_code == 200
    assert len(forwarded) == 1


@pytest.mark.parametrize("role", [UserRole.PLATFORM_ADMIN, UserRole.OWNER])
def test_inactive_or_non_tenant_roles_cannot_use_the_data_proxy(monkeypatch, role):
    response, forwarded = request_as(
        monkeypatch, role, "GET", "v1/fields/f1/soil/profile", active=role != UserRole.OWNER
    )
    assert response.status_code == 403
    assert forwarded == []


@pytest.mark.parametrize(
    "path",
    [
        "internal/admin",
        "v1/soil/production-certifications",
        "v1/soil/calibrations/build",
        "metrics",
        "v1/fields/%252e%252e/soil/profile",
    ],
)
def test_unpublished_or_ambiguous_paths_never_receive_a_service_token(monkeypatch, path):
    response, forwarded = request_as(monkeypatch, UserRole.OWNER, "POST", path)
    assert response.status_code == 404
    assert forwarded == []


def test_a_read_path_is_not_implicitly_a_write_path(monkeypatch):
    response, forwarded = request_as(
        monkeypatch, UserRole.OWNER, "DELETE", "v1/fields/f1/soil/profile"
    )
    assert response.status_code == 405
    assert forwarded == []


def test_viewer_is_denied_with_the_full_platform_middleware(monkeypatch):
    response, forwarded = request_as(
        monkeypatch, UserRole.VIEWER, "POST", "v1/soil/ingest", full_platform=True
    )
    assert response.status_code == 403
    assert forwarded == []


def test_platform_admin_can_check_health_without_accessing_soil_data(monkeypatch):
    response, forwarded = request_as(monkeypatch, UserRole.PLATFORM_ADMIN, "GET", "healthz")
    assert response.status_code == 200
    assert len(forwarded) == 1
