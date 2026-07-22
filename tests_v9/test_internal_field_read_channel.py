#!/usr/bin/env python3
"""Internal field-read channel — ownership moved to field-management-service.

The tenant-scoped internal field READ (GET /internal/fields[/{id}]) is now owned by
field-management-service (the declared owner of the `fields` table per
docs/architecture/db_ownership.yml). This pins the post-move contract:

  • the PLATFORM no longer exposes /api/v1/internal/fields[/{field_id}] (route budget
    returns to baseline; ownership is single-owner).
  • field-management-service exposes the routes, service-token protected, fail-closed
    at 401 (a user Bearer JWT with no X-Agent-Token is rejected), tenant from the
    X-Tenant-Id header (missing ⇒ 400), scoped by field_id AND tenant_id ⇒ 404.
  • vegetation reads fields from FIELD_SERVICE_URL/internal/fields[...] with its
    service token — never the public JWT-protected platform routes, never a platform
    fallback.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
VEG = os.path.join(ROOT, "services/vegetation-analysis-service")
FIELD_SVC = os.path.join(ROOT, "services/field-management-service")
PLATFORM_INTERNAL_SRC = os.path.join(CORE, "api/routers/internal_service.py")


# ── Platform: the internal field READ routes are GONE (moved to the field owner) ──
@pytest.fixture(scope="module")
def app_mod():
    pytest.importorskip("fastapi")
    added = CORE not in sys.path
    if added:
        sys.path.insert(0, CORE)
    import api.main as m

    yield m
    if added and CORE in sys.path:
        sys.path.remove(CORE)


def test_platform_no_longer_hosts_internal_field_read(app_mod):
    paths = {getattr(r, "path", None) for r in app_mod.app.routes}
    assert "/api/v1/internal/fields/{field_id}" not in paths
    assert "/api/v1/internal/fields" not in paths


def test_platform_internal_source_dropped_the_read_routes():
    src = open(PLATFORM_INTERNAL_SRC, encoding="utf-8").read()
    assert "def internal_get_field(" not in src
    assert "def internal_list_fields(" not in src
    # the field-state / ai-advice internal routes remain
    assert "def internal_field_state(" in src
    assert "def internal_ai_advice_event(" in src


# ── field-management-service: owns the routes + fail-closed 401 guard ──
@pytest.fixture(scope="module")
def field_mod():
    pytest.importorskip("fastapi")
    spec = importlib.util.spec_from_file_location(
        "field_management_main_channel_test", os.path.join(FIELD_SVC, "main.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_field_service_registers_internal_routes(field_mod):
    paths = {getattr(r, "path", None) for r in field_mod.app.routes}
    assert "/internal/fields/{field_id}" in paths
    assert "/internal/fields" in paths


def test_field_service_token_guard_is_fail_closed_401(monkeypatch, field_mod):
    from fastapi import HTTPException

    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    with pytest.raises(HTTPException) as e1:  # no secret configured ⇒ always rejected
        field_mod._require_service_token("anything")
    assert e1.value.status_code == 401  # this service's contract is 401, not 403

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "s3cr3t")
    with pytest.raises(HTTPException) as e2:  # wrong token ⇒ rejected
        field_mod._require_service_token("wrong")
    assert e2.value.status_code == 401
    assert field_mod._require_service_token("s3cr3t") is None  # match ⇒ passes


def test_field_service_tenant_required(field_mod):
    from fastapi import HTTPException

    # ``request`` is the first positional param (used only for method/path binding of
    # the tenant assertion); a missing X-Tenant-Id fails closed at 400 before it is read.
    with pytest.raises(HTTPException) as e:
        field_mod._require_tenant(request=None, x_tenant_id=None)
    assert e.value.status_code == 400


def test_field_service_source_contract():
    src = open(os.path.join(FIELD_SVC, "main.py"), encoding="utf-8").read()
    # service-token only — no user-JWT permission dependency / JWT decode is invoked
    # (paren/import-qualified so honest docstring prose does not false-positive).
    assert "require_permission(" not in src and "get_current_user(" not in src
    assert "jwt.decode(" not in src and "import jwt" not in src
    # scoped by BOTH field_id AND tenant_id; missing/other-tenant ⇒ 404
    assert "WHERE field_id = $1 AND tenant_id = $2::uuid" in src
    assert "status_code=404" in src
    # tenant from the verified header (missing ⇒ 400), fail-closed DB (⇒ 503)
    assert 'Header(None, alias="X-Tenant-Id")' in src
    assert "status_code=400" in src and "status_code=503" in src
    # no platform fallback — this service IS the field owner
    assert "PLATFORM_API_URL" not in src


# ── Vegetation: reads via the field-service channel with the right URL + headers ──
class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload

    def json(self):
        return self._p


class _FakeClient:
    def __init__(self, resp, sink):
        self._resp = resp
        self._sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        self._sink.append((url, headers))
        return self._resp


@pytest.fixture(scope="module")
def veg_mod():
    pytest.importorskip("httpx")
    pytest.importorskip("fastapi")  # vegetation_runtime imports fastapi at module load
    added = VEG not in sys.path
    if added:
        sys.path.insert(0, VEG)
    try:
        spec = importlib.util.spec_from_file_location(
            "sahool_vegetation_runtime_under_test", os.path.join(VEG, "vegetation_runtime.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if added and VEG in sys.path:
            sys.path.remove(VEG)


def test_vegetation_never_calls_public_or_platform_field_routes():
    veg_src = open(os.path.join(VEG, "vegetation_runtime.py"), encoding="utf-8").read()
    import re as _re

    # No public JWT field route, and no platform-based field read at all.
    public_calls = _re.findall(r"\{PLATFORM_API_URL\}/api/v1/(?:internal/)?fields", veg_src)
    assert public_calls == [], f"vegetation still reads fields from the platform: {public_calls}"
    assert "{FIELD_SERVICE_URL}/internal/fields/{field_id}" in veg_src
    assert '{FIELD_SERVICE_URL}/internal/fields"' in veg_src


@pytest.mark.asyncio
async def test_load_field_uses_field_service_channel_with_headers(veg_mod, monkeypatch):
    monkeypatch.setattr(veg_mod, "FIELD_SERVICE_URL", "http://field-management:8000")
    monkeypatch.setattr(veg_mod, "RASTER_SERVICE_TOKEN", "svc-tkn")
    # A tenant-scoped read must carry a caller-bound tenant assertion (field-catalog
    # caller boundary): the signing key is required or the call fails closed at 503.
    monkeypatch.setattr(
        veg_mod, "FIELD_SERVICE_TENANT_ASSERTION_KEY", "assertion-signing-key-at-least-32-chars"
    )
    sink: list = []
    # 404 (other-tenant/missing) ⇒ fail-soft None, but the call is still recorded.
    monkeypatch.setattr(
        veg_mod.httpx, "AsyncClient", lambda *a, **k: _FakeClient(_Resp(404, {}), sink)
    )
    out = await veg_mod._load_field_from_db("fld_1", "tenant-1")
    assert out is None  # non-200 ⇒ None (no masked field data)
    url, headers = sink[0]
    assert url.endswith("/internal/fields/fld_1")
    assert headers["X-Agent-Token"] == "svc-tkn"
    assert headers["X-Tenant-Id"] == "tenant-1"
    # the signed, caller/method/path-bound assertion accompanies the tenant header
    assert headers["X-Tenant-Assertion"]
    assert headers["X-Service-Name"] == veg_mod.FIELD_SERVICE_CALLER


@pytest.mark.asyncio
async def test_load_field_none_without_field_service_url(veg_mod, monkeypatch):
    monkeypatch.setattr(veg_mod, "FIELD_SERVICE_URL", "")
    monkeypatch.setattr(veg_mod, "RASTER_SERVICE_TOKEN", "svc-tkn")
    assert await veg_mod._load_field_from_db("fld_1", "tenant-1") is None
