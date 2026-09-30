"""SENTINEL-HUB-MCP-01 — المستأجِر من التوكن، والحقول من مالكها، ونقاط Copernicus Data Space.

ثلاثة عيوبٍ قاسها التدقيق الحيّ (2026-09-29) وأُعيد قياسها هنا عبر نقطة HTTP الحقيقيّة
(``POST /v1/mcp/tools/call`` بتوكن JWT حقيقيّ لمستأجِر ``CALLER``):

1. ``read_indicator_observation``/``analyze_field_change`` مرّرا ``tenant_id`` **من وسائط الأداة**
   ترويسةً إلى raster-service بلا توكن خدمة: حاملُ ``satellite:read`` يسمّي مستأجِرَ غيره.
2. أداتا الجلب حلّتا ``field_id`` من ثمانية حقولٍ تجريبيّة (``field_01``…) بحدودٍ مخترَعة،
   وأيُّ حقلٍ حقيقيّ ⇒ 404.
3. العنوان ``services.sentinel-hub.com`` التجاريّ مع اعتمادات عميلٍ على realm الـCDSE.

الخادمُ يُحمَّل كما تبنيه صورتُه (``shared/`` الجذر و``mcp_servers/shared`` حزمةً واحدة)، ولا
يُبدَّل إلّا **النقل** (``httpx.MockTransport``) فيُرى كلُّ طلبٍ صادر: وجهتُه ومستأجِرُه واعتمادُه.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "services" / "mcp_servers"
RASTER_CDSE = ROOT / "services" / "raster-service" / "cdse_client.py"
TOKEN = "svc-token-mcp-fixture"
KEY = "k" * 40
CALLER, VICTIM = "tenant-caller", "tenant-victim"
FIELD = "fld_real_123"
POLYGON = {
    "type": "Polygon",
    "coordinates": [[[44.1, 15.3], [44.2, 15.3], [44.2, 15.4], [44.1, 15.4], [44.1, 15.3]]],
}


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _jwt(tenant=CALLER):
    import jwt

    now = int(time.time())
    claims = {
        "sub": "42",
        "tenant_id": tenant,
        "scope": "satellite:read",
        "iss": "sahool-auth",
        "aud": "sahool",
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode(claims, "x" * 40, algorithm="HS256")


class Upstream:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.field_status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        if "raster" in host:
            body = {"real_data": True, "stats": {"mean": 0.61}, "date": "2026-09-01"}
            return httpx.Response(200, json={**body, "available": False, "points": []})
        if "field-management" in host:
            owned = path == f"/internal/fields/{FIELD}" and request.headers["x-tenant-id"] == CALLER
            if self.field_status != 200:
                return httpx.Response(self.field_status, json={})
            if not owned:
                return httpx.Response(404, json={"detail": "field not found for this tenant"})
            return httpx.Response(200, json={"field_id": FIELD, "geometry": POLYGON})
        if path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "provider-token"})
        return httpx.Response(200, content=b"TIFF")

    def to(self, fragment: str) -> list[httpx.Request]:
        return [r for r in self.requests if fragment in str(r.url)]


@pytest.fixture
def mcp(monkeypatch):
    import shared

    monkeypatch.setattr(shared, "__path__", [str(ROOT / "shared"), str(MCP / "shared")])
    monkeypatch.syspath_prepend(str(MCP))
    oauth = _load("_sentinel_t2_oauth", MCP / "shared/oauth_middleware.py")
    monkeypatch.setitem(sys.modules, "shared.oauth_middleware", oauth)
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("FIELD_SERVICE_TENANT_ASSERTION_KEY", KEY)
    monkeypatch.setenv("SH_CLIENT_ID", "cdse-client")
    monkeypatch.setenv("SH_CLIENT_SECRET", "cdse-secret")
    monkeypatch.delenv("CDSE_CLIENT_ID", raising=False)
    monkeypatch.delenv("CDSE_CLIENT_SECRET", raising=False)
    module = _load("_sentinel_t2_server", MCP / "sentinel_hub_server.py")
    monkeypatch.setattr(module, "FIELD_SERVICE_URL", "http://sahool-field-management:8000")
    monkeypatch.setattr(module, "IDEMPOTENCY_CACHE", {})
    upstream = Upstream()
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(upstream)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    return module, upstream


def _call(module, name, arguments, tenant=CALLER):
    client = TestClient(module.app)
    return client.post(
        "/v1/mcp/tools/call",
        json={"name": name, "arguments": arguments},
        headers={"Authorization": "Bearer " + _jwt(tenant)},
    )


# ── ١) المستأجِر ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tool", ["read_indicator_observation", "analyze_field_change"])
def test_a_tenant_named_in_the_arguments_cannot_override_the_token(mcp, tool):
    module, upstream = mcp
    resp = _call(module, tool, {"field_id": "F-1", "tenant_id": VICTIM})
    assert resp.status_code == 403 and resp.json()["detail"] == "tenant_mismatch"
    assert upstream.requests == [], "nothing may leave the server for a mismatched tenant"


@pytest.mark.parametrize("tool", ["read_indicator_observation", "analyze_field_change"])
def test_raster_reads_assert_the_token_tenant_with_the_service_credential(mcp, tool):
    module, upstream = mcp
    for arguments in ({"field_id": "F-1"}, {"field_id": "F-1", "tenant_id": CALLER}):
        upstream.requests.clear()
        resp = _call(module, tool, arguments)
        assert resp.status_code in (200, 424), resp.text  # 424: السلسلة الفارغة صادقة
        (sent,) = upstream.to("sahool-raster-service")
        assert sent.headers["x-tenant-id"] == CALLER
        assert sent.headers["x-agent-token"] == TOKEN


def test_without_the_service_credential_no_tenant_claim_is_sent(mcp, monkeypatch):
    module, upstream = mcp
    monkeypatch.delenv("SAHOOL_AGENT_TOKEN")
    resp = _call(module, "read_indicator_observation", {"field_id": "F-1"})
    assert resp.status_code == 503
    assert upstream.requests == []


# ── ٢) الحقول من مالكها لا من سجلٍّ تجريبيّ ─────────────────────────────────────


def test_no_demo_field_registry_remains(mcp):
    module, _ = mcp
    assert not hasattr(module, "FIELD_REGISTRY")
    source = (MCP / "sentinel_hub_server.py").read_text(encoding="utf-8")
    assert not re.search(r"\bfield_0[1-8]\b", source)


def test_a_demo_field_id_is_now_just_an_unknown_field(mcp):
    module, upstream = mcp
    resp = _call(module, "fetch_sentinel2_l2a", {"field_id": "field_01", "date_range": "a/b"})
    assert resp.status_code == 404
    assert not upstream.to("/api/v1/process"), "no provider call for an unresolved field"


def test_a_real_field_resolves_from_its_owner_with_a_verifiable_assertion(mcp):
    from shared.security.service_tenant_assertion import verify_tenant_assertion

    module, upstream = mcp
    resp = _call(
        module, "fetch_sentinel2_l2a", {"field_id": FIELD, "date_range": "2026-09-01/2026-09-10"}
    )
    assert resp.status_code == 200, resp.text
    (owner,) = upstream.to("/internal/fields/")
    headers = owner.headers
    assert headers["x-tenant-id"] == CALLER and headers["x-agent-token"] == TOKEN
    # the same verifier field-management-service runs (services/field-management-service/main.py)
    verify_tenant_assertion(
        headers["x-tenant-assertion"],
        {"current": KEY},
        headers["x-service-name"],
        CALLER,
        expected_method="GET",
        expected_path=owner.url.path,
        expected_request_id=headers["x-request-id"],
    )
    assert headers["x-service-name"] == "sentinel-hub-mcp"
    (process,) = upstream.to("/api/v1/process")
    import json

    assert json.loads(process.content)["input"]["bounds"]["bbox"] == [44.1, 15.3, 44.2, 15.4]


def test_another_tenants_field_is_indistinguishable_from_a_missing_one(mcp):
    module, upstream = mcp
    resp = _call(
        module, "fetch_sentinel2_l2a", {"field_id": FIELD, "date_range": "a/b"}, tenant=VICTIM
    )
    assert resp.status_code == 404
    assert not upstream.to("/api/v1/process")


@pytest.mark.parametrize("status, expected", [(401, 502), (403, 502), (500, 503)])
def test_owner_failures_are_declared_never_replaced_by_a_guess(mcp, status, expected):
    module, upstream = mcp
    upstream.field_status = status
    resp = _call(module, "fetch_sentinel1_grd", {"field_id": FIELD, "date_range": "a/b"})
    assert resp.status_code == expected
    assert not upstream.to("/api/v1/process")


def test_an_unconfigured_field_source_is_an_explicit_error(mcp, monkeypatch):
    module, upstream = mcp
    monkeypatch.setattr(module, "FIELD_SERVICE_URL", "")
    resp = _call(module, "fetch_sentinel2_l2a", {"field_id": FIELD, "date_range": "a/b"})
    assert resp.status_code == 503 and "field_source_unconfigured" in resp.json()["detail"]
    assert upstream.requests == []


# ── ٣) نقاط CDSE ─────────────────────────────────────────────────────────────


def test_fetch_uses_the_copernicus_data_space_endpoints(mcp):
    module, upstream = mcp
    resp = _call(
        module, "fetch_sentinel2_l2a", {"field_id": FIELD, "date_range": "2026-09-01/2026-09-10"}
    )
    assert resp.status_code == 200, resp.text
    hosts = {r.url.host for r in upstream.requests}
    assert "services.sentinel-hub.com" not in hosts
    token = upstream.to("/protocol/openid-connect/token")
    assert token and token[0].url.host == "identity.dataspace.copernicus.eu"
    assert upstream.to("/api/v1/process")[0].url.host == "sh.dataspace.copernicus.eu"


def test_missing_cdse_credentials_are_an_explicit_error(mcp, monkeypatch):
    module, upstream = mcp
    monkeypatch.delenv("SH_CLIENT_ID")
    resp = _call(module, "fetch_sentinel2_l2a", {"field_id": FIELD, "date_range": "a/b"})
    assert resp.status_code == 503
    assert not upstream.to("/api/v1/process")


def test_cdse_defaults_match_the_canonical_raster_client():
    """نسختان من العنوان تنجرفان: القيمُ الافتراضيّة هنا هي قيمُ المالك القانونيّ حرفيّاً."""
    pattern = r'os\.getenv\(\s*"{name}",\s*"([^"]+)"'
    raster = RASTER_CDSE.read_text(encoding="utf-8")
    mcp_src = (MCP / "sentinel_hub_server.py").read_text(encoding="utf-8")
    for name in ("SH_TOKEN_URL", "SH_BASE_URL"):
        canonical = re.search(pattern.format(name=name), raster)
        ours = re.search(pattern.format(name=name), mcp_src)
        assert canonical and ours and canonical.group(1) == ours.group(1), name
