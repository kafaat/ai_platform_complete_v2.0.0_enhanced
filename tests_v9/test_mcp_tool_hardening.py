"""MCP tool hardening: tenant identity, field ids, procurement approval, cache bounds.

Each test drives the real FastAPI apps (or the real tool functions) in-process;
only the upstream HTTP call / database connection is replaced.

* sentinel_hub_server: the raster tools must send the *token's* tenant to
  raster-service, refuse a different tenant in the arguments (403), and refuse a
  field_id that is not a plain identifier (422) instead of putting it in the path.
* market_server: the auto-approval threshold is server configuration, an order
  with an unpriced item is never auto-approved, and the REST write routes need
  ``market:write`` just like the MCP write tools.
* generic_context_server: echoed caller values are not verified/governing and
  the tenant comes from the token.
* weather/wofost/sentinel: the idempotency cache evicts expired and oldest
  entries instead of growing without bound.
* wofost_server: ``get_crop_parameters`` no longer serves invented parameters.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "services/mcp_servers"
SECRET = "x" * 40


def _load(name: str, path: Path):
    current = sys.modules.get(name)
    if current is not None:
        assert Path(getattr(current, "__file__", "")).resolve() == path.resolve()
        return current
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mcp_env(monkeypatch):
    """Container-equivalent import layout: both shared dirs under one package."""
    import shared

    monkeypatch.setattr(shared, "__path__", [str(ROOT / "shared"), str(MCP / "shared")])
    monkeypatch.syspath_prepend(str(MCP))
    oauth = _load("_live_mcp_oauth", MCP / "shared/oauth_middleware.py")
    monkeypatch.setitem(sys.modules, "shared.oauth_middleware", oauth)
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("SAHOOL_ALLOW_HS256_IN_PROD", raising=False)
    return oauth


def _token(tenant: str = "tenant-a", scope: str = "satellite:read", **claims) -> str:
    import jwt

    payload = {
        "sub": "42",
        "tenant_id": tenant,
        "scope": scope,
        "iss": "sahool-auth",
        "aud": "sahool",
        "exp": int(time.time()) + 300,
    }
    payload.update(claims)
    return jwt.encode(payload, SECRET, algorithm="HS256")


def _auth(**kwargs) -> dict:
    return {"Authorization": "Bearer " + _token(**kwargs)}


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app, raise_server_exceptions=False)


# ── sentinel_hub_server: raster reads ───────────────────────────────────────


@pytest.fixture
def sentinel(mcp_env, monkeypatch):
    module = _load("_live_sentinel_hub_server", MCP / "sentinel_hub_server.py")
    monkeypatch.setattr(module, "IDEMPOTENCY_CACHE", {})
    calls: list[dict] = []

    async def fake_retry_request(method, url, **kwargs):
        import httpx

        calls.append({"url": url, **kwargs})
        if url.endswith("/indicator-grid"):
            body = {
                "real_data": True,
                "source": "cog",
                "stats": {"mean": 0.5},
                "date": "2026-01-01",
            }
        else:
            body = {"available": False, "points": []}
        return httpx.Response(200, json=body)

    monkeypatch.setattr(module, "retry_request", fake_retry_request)
    return module, calls


@pytest.mark.parametrize("tool", ["read_indicator_observation", "analyze_field_change"])
def test_sentinel_rejects_argument_tenant_that_differs_from_token(sentinel, tool):
    module, calls = sentinel
    response = _client(module.app).post(
        "/v1/mcp/tools/call",
        json={"name": tool, "arguments": {"field_id": "field_01", "tenant_id": "tenant-b"}},
        headers=_auth(tenant="tenant-a"),
    )
    assert response.status_code == 403, response.text
    assert calls == []


def test_sentinel_sends_token_tenant_to_raster_service(sentinel):
    module, calls = sentinel
    client = _client(module.app)
    for arguments in (
        {"field_id": "field_01"},
        {"field_id": "field_01", "tenant_id": "tenant-a"},
    ):
        response = client.post(
            "/v1/mcp/tools/call",
            json={"name": "read_indicator_observation", "arguments": arguments},
            headers=_auth(tenant="tenant-a"),
        )
        assert response.status_code == 200, response.text
        payload = json.loads(response.json()["content"][0]["text"])
        assert payload["tenant_id"] == "tenant-a"
    assert [call["headers"]["X-Tenant-Id"] for call in calls] == ["tenant-a", "tenant-a"]


@pytest.mark.parametrize("tool", ["read_indicator_observation", "analyze_field_change"])
@pytest.mark.parametrize(
    "field_id", ["../../admin", "field_01/../x", "a?b=1", "f%2F..", "x" * 65, "field 01"]
)
def test_sentinel_rejects_field_id_that_is_not_an_identifier(sentinel, tool, field_id):
    module, calls = sentinel
    response = _client(module.app).post(
        "/v1/mcp/tools/call",
        json={"name": tool, "arguments": {"field_id": field_id, "tenant_id": "tenant-a"}},
        headers=_auth(tenant="tenant-a"),
    )
    assert response.status_code == 422, response.text
    assert calls == []


def test_sentinel_accepts_uuid_field_id(sentinel):
    module, calls = sentinel
    field_id = "3f2a9c1e-0b7d-4e5a-9c2f-1a2b3c4d5e6f"
    response = _client(module.app).post(
        "/v1/mcp/tools/call",
        json={"name": "read_indicator_observation", "arguments": {"field_id": field_id}},
        headers=_auth(tenant="tenant-a"),
    )
    assert response.status_code == 200, response.text
    assert calls[0]["url"].endswith(f"/v1/fields/{field_id}/indicator-grid")


# ── market_server: procurement approval and write scope ─────────────────────


class _FakeConn:
    def __init__(self):
        self.statements: list[tuple] = []

    async def fetchval(self, sql, *params):
        self.statements.append((sql, params))
        return "00000000-0000-0000-0000-0000000000aa"

    async def execute(self, sql, *params):
        self.statements.append((sql, params))


@pytest.fixture
def market(mcp_env, monkeypatch):
    module = _load("_hard_market_server", MCP / "market_server.py")
    monkeypatch.setattr(module, "JWT_SECRET", SECRET)
    monkeypatch.delenv("MARKET_AUTO_APPROVE_BELOW_USD", raising=False)
    conns: list[_FakeConn] = []

    @asynccontextmanager
    async def fake_tenant_connection(tenant_id):
        conn = _FakeConn()
        conns.append(conn)
        yield conn

    monkeypatch.setattr(module, "tenant_connection", fake_tenant_connection)
    return module, conns


def _final_status(conn: _FakeConn) -> str:
    updates = [p for sql, p in conn.statements if sql.lstrip().startswith("UPDATE")]
    assert len(updates) == 1
    return updates[0][0]


async def _procure(module, items, **extra):
    return await module.tool_create_procurement({"tenant_id": "tenant-a", "items": items, **extra})


async def test_market_caller_cannot_raise_auto_approve_threshold(market):
    module, conns = market
    items = [{"product_name": "urea", "quantity": 10, "max_unit_price_usd": 1000}]
    result = await _procure(module, items, auto_approve_below_usd=10**12)
    assert result["status"] == "pending_approval" and result["auto_approved"] is False
    assert _final_status(conns[-1]) == "pending_approval"
    insert_params = conns[-1].statements[0][1]
    assert insert_params[-1] == 500.0  # threshold recorded is the server's, not the caller's


@pytest.mark.parametrize("price", [None, 0, -5, "NaN", "Infinity", float("nan")], ids=repr)
async def test_market_unpriced_item_is_never_auto_approved(market, price):
    module, conns = market
    item = {"product_name": "seed", "quantity": 1}
    if price is not None:
        item["max_unit_price_usd"] = price
    priced = {"product_name": "urea", "quantity": 1, "max_unit_price_usd": 1}
    result = await _procure(module, [priced, item])
    assert result["status"] == "pending_approval" and result["auto_approved"] is False
    assert _final_status(conns[-1]) == "pending_approval"


async def test_market_small_fully_priced_order_is_still_auto_approved(market):
    module, conns = market
    items = [{"product_name": "urea", "quantity": 2, "max_unit_price_usd": 10}]
    result = await _procure(module, items)
    assert result["status"] == "approved" and result["auto_approved"] is True
    assert _final_status(conns[-1]) == "approved"


async def test_market_threshold_comes_from_server_environment(market, monkeypatch):
    module, conns = market
    monkeypatch.setenv("MARKET_AUTO_APPROVE_BELOW_USD", "50")
    items = [{"product_name": "urea", "quantity": 10, "max_unit_price_usd": 10}]
    result = await _procure(module, items, auto_approve_below_usd=1000)
    assert result["status"] == "pending_approval"


@pytest.mark.parametrize(
    "path,body",
    [
        (
            "/v1/procurement",
            {"items": [{"product_name": "urea", "quantity": 1, "max_unit_price_usd": 1}]},
        ),
        ("/v1/sales", {"crop_type": "wheat", "quantity_kg": 10, "price_per_kg_usd": 1}),
    ],
)
def test_market_rest_writes_require_market_write(market, path, body):
    module, conns = market
    client = _client(module.app)
    denied = client.post(path, json=body, headers=_auth(scope="market:read"))
    assert denied.status_code == 403, denied.text
    assert conns == []
    allowed = client.post(path, json=body, headers=_auth(scope="market:read market:write"))
    assert allowed.status_code not in (401, 403), allowed.text
    assert conns, "market:write caller should reach the write path"


# ── generic_context_server: echoed values ───────────────────────────────────


@pytest.fixture
def generic(mcp_env, monkeypatch):
    monkeypatch.setenv("MCP_SERVICE", "lab")
    return _load("_hard_generic_context_lab", MCP / "generic_context_server.py")


def test_generic_context_echo_is_not_verified_or_governing(generic):
    response = _client(generic.app).post(
        "/v1/mcp/tools/call",
        json={
            "name": "get_lab_context",
            "arguments": {"field_id": "f1", "tenant_id": "tenant-b", "soil_ec": 99.0},
        },
        headers=_auth(tenant="tenant-a", scope=generic.MCP_CONTEXT_SCOPE),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verified"] is False
    assert body.get("governing", False) is False
    assert body["tenant_id"] == "tenant-a"


# ── idempotency cache bounds ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "module_name,scope,executor",
    [
        ("weather_server", "weather:read", "_execute"),
        ("wofost_server", "crop:read", "_execute"),
        ("sentinel_hub_server", "satellite:read", "_execute_tool"),
    ],
)
def test_idempotency_cache_is_bounded(mcp_env, monkeypatch, module_name, scope, executor):
    module = _load("_live_" + module_name, MCP / (module_name + ".py"))
    monkeypatch.setattr(module, "IDEMPOTENCY_CACHE", {})
    monkeypatch.setitem(
        module.idempotency_cache_put.__globals__, "IDEMPOTENCY_CACHE_MAX_ENTRIES", 3
    )
    calls = []

    async def execute(*args):
        calls.append(args)
        return {"content": [{"type": "text", "text": str(len(calls))}]}

    monkeypatch.setattr(module, executor, execute)
    client = _client(module.app)
    headers = _auth(scope=scope)
    for i in range(6):
        body = {"name": "probe", "arguments": {}, "request_id": f"r{i}"}
        assert client.post("/v1/mcp/tools/call", json=body, headers=headers).status_code == 200
    assert len(module.IDEMPOTENCY_CACHE) == 3
    # The newest key is still served from cache; the oldest was evicted.
    newest = {"name": "probe", "arguments": {}, "request_id": "r5"}
    client.post("/v1/mcp/tools/call", json=newest, headers=headers)
    assert len(calls) == 6
    oldest = {"name": "probe", "arguments": {}, "request_id": "r0"}
    client.post("/v1/mcp/tools/call", json=oldest, headers=headers)
    assert len(calls) == 7


def test_idempotency_cache_drops_expired_entries(mcp_env):
    oauth = mcp_env
    cache: dict = {}
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    oauth.idempotency_cache_put(cache, "a", 1, ttl_seconds=10, now=t0)
    assert oauth.idempotency_cache_get(cache, "a", now=t0 + timedelta(seconds=5)) == 1
    oauth.idempotency_cache_put(cache, "b", 2, ttl_seconds=10, now=t0 + timedelta(seconds=11))
    assert list(cache) == ["b"]
    assert oauth.idempotency_cache_get(cache, "b", now=t0 + timedelta(seconds=21)) is None
    assert cache == {}
    oauth.idempotency_cache_put(cache, None, 3, ttl_seconds=10)
    assert cache == {}


# ── wofost_server: no invented crop parameters ──────────────────────────────


@pytest.mark.parametrize("crop", ["wheat", "potato", "millet"])
def test_wofost_get_crop_parameters_serves_no_invented_values(mcp_env, monkeypatch, crop):
    module = _load("_live_wofost_server", MCP / "wofost_server.py")
    monkeypatch.setattr(module, "IDEMPOTENCY_CACHE", {})
    response = _client(module.app).post(
        "/v1/mcp/tools/call",
        json={"name": "get_crop_parameters", "arguments": {"crop": crop}, "request_id": "p"},
        headers=_auth(scope="crop:read"),
    )
    assert response.status_code == 501, response.text
    assert "tsum1" not in response.text.lower()
    assert module.IDEMPOTENCY_CACHE == {}
