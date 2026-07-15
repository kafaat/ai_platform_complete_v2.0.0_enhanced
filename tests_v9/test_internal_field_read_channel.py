"""Service-to-service internal field read (vegetation → platform field owner).

Fixes the /v1/analyze 404 that masked a 401: vegetation held a service token but
called the JWT-protected public GET /api/v1/fields/{id}. It now calls the
service-token internal read GET /api/v1/internal/fields/{id} with the JWT-derived
X-Tenant-Id. This pins the SEC-3 contract:

  service token valid + tenant valid        → 200 (route reachable, guard passes)
  service token missing/wrong               → 403 (fail-closed guard)
  tenant missing                            → 400
  field owned by another tenant / missing   → 404 (no existence disclosure)
  user JWT only on the internal route       → rejected (no require_permission here)
  forged X-Tenant-Id from a browser         → rejected (needs the service token too)
  vegetation reads via the internal channel with X-Agent-Token + X-Tenant-Id header
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
INTERNAL_SRC = os.path.join(CORE, "api/routers/internal_service.py")


# ── Platform: route registered + service-token protected + honest contract ──
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


def test_internal_field_read_route_registered(app_mod):
    paths = {getattr(r, "path", None) for r in app_mod.app.routes}
    assert "/api/v1/internal/fields/{field_id}" in paths
    assert "/api/v1/internal/fields" in paths  # list route (same SEC-3 contract)


def test_vegetation_never_calls_public_jwt_field_routes():
    # Regression guard: both the by-id read and the list must go through the
    # service-token internal routes. A live GET against the public JWT-protected
    # /api/v1/fields would 401 → the masked-404 / 503 bug returns.
    veg_src = open(os.path.join(VEG, "vegetation_runtime.py"), encoding="utf-8").read()
    import re as _re

    public_calls = _re.findall(
        r'\.get\(\s*\n?\s*f?"\{PLATFORM_API_URL\}/api/v1/fields[/"]', veg_src
    )
    assert public_calls == [], f"vegetation still calls the public JWT field route: {public_calls}"
    assert "{PLATFORM_API_URL}/api/v1/internal/fields/{field_id}" in veg_src
    assert '{PLATFORM_API_URL}/api/v1/internal/fields"' in veg_src


def test_service_token_guard_is_fail_closed(monkeypatch):
    from api.routers.internal_service import _require_service_token
    from fastapi import HTTPException

    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    with pytest.raises(HTTPException) as e1:  # no secret configured ⇒ always rejected
        _require_service_token("anything")
    assert e1.value.status_code == 403

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "s3cr3t")
    with pytest.raises(HTTPException) as e2:  # wrong token ⇒ rejected
        _require_service_token("wrong")
    assert e2.value.status_code == 403
    assert _require_service_token("s3cr3t") is None  # match ⇒ passes


def test_internal_route_source_contract():
    src = open(INTERNAL_SRC, encoding="utf-8").read()
    block = src[src.index("async def internal_get_field(") :]
    block = block[: block.index("\n\n\n") if "\n\n\n" in block else len(block)]
    # service-token only — never the public user-JWT permission dependency
    assert "Depends(_require_service_token)" in block
    assert "require_permission" not in block and "get_current_user" not in block
    # tenant from the verified header, not body/query
    assert 'Header(None, alias="X-Tenant-Id")' in src
    assert "Query(" not in block
    # missing tenant ⇒ 400
    assert "status_code=400" in block
    # scoped by BOTH field_id AND tenant_id; missing/other-tenant ⇒ 404
    assert "WHERE field_id = $1 AND tenant_id = $2::uuid" in block
    assert "status_code=404" in block


# ── Vegetation: reads via the internal channel with the right URL + headers ──
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


@pytest.mark.asyncio
async def test_load_field_uses_internal_channel_with_headers(veg_mod, monkeypatch):
    monkeypatch.setattr(veg_mod, "PLATFORM_API_URL", "http://platform:8000")
    monkeypatch.setattr(veg_mod, "RASTER_SERVICE_TOKEN", "svc-tkn")
    sink: list = []
    # 404 (other-tenant/missing) ⇒ fail-soft None, but the call is still recorded.
    monkeypatch.setattr(
        veg_mod.httpx, "AsyncClient", lambda *a, **k: _FakeClient(_Resp(404, {}), sink)
    )
    out = await veg_mod._load_field_from_db("fld_1", "tenant-1")
    assert out is None  # non-200 ⇒ None (no masked field data)
    url, headers = sink[0]
    assert url.endswith("/api/v1/internal/fields/fld_1")
    assert headers["X-Agent-Token"] == "svc-tkn"
    assert headers["X-Tenant-Id"] == "tenant-1"


@pytest.mark.asyncio
async def test_load_field_none_without_platform_url(veg_mod, monkeypatch):
    monkeypatch.setattr(veg_mod, "PLATFORM_API_URL", "")
    monkeypatch.setattr(veg_mod, "RASTER_SERVICE_TOKEN", "svc-tkn")
    assert await veg_mod._load_field_from_db("fld_1", "tenant-1") is None
