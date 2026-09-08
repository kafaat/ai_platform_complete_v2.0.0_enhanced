"""MCP protected body routes authenticate before request-body validation."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "services/mcp_servers"


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


def test_missing_token_beats_malformed_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _load("shared.oauth_middleware", MCP / "shared/oauth_middleware.py")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("MCP_SERVICE", "field")
    mod = _load("_mcp_auth_first_generic_context", MCP / "generic_context_server.py")
    client = TestClient(mod.app)
    response = client.post(
        "/v1/mcp/tools/call",
        content=b'{"name":',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 401, response.text


def test_missing_token_beats_schema_validation() -> None:
    mod = sys.modules["_mcp_auth_first_generic_context"]
    response = TestClient(mod.app).post("/v1/mcp/tools/call", json={})
    assert response.status_code == 401, response.text


@pytest.fixture
def live_mcp_contract(monkeypatch):
    """Load real transport/auth/apps, with only vendor/DB I/O replaced in tests."""
    import shared

    monkeypatch.setattr(shared, "__path__", [str(ROOT / "shared"), str(MCP / "shared")])
    monkeypatch.syspath_prepend(str(MCP))
    monkeypatch.syspath_prepend(str(ROOT / "services/supervisor-agent"))
    oauth = _load("_live_mcp_oauth", MCP / "shared/oauth_middleware.py")
    monkeypatch.setitem(sys.modules, "shared.oauth_middleware", oauth)
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("SAHOOL_ALLOW_HS256_IN_PROD", raising=False)
    transport = _load("_live_mcp_transport", ROOT / "services/supervisor-agent/mcp_client.py")
    import circuit_breaker

    monkeypatch.setattr(circuit_breaker, "mcp_breakers", circuit_breaker.CircuitBreakerRegistry())
    return transport, oauth


def _caller_token(tenant="tenant-a", scope="weather:read", **claims):
    import time

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
    return jwt.encode(payload, "x" * 40, algorithm="HS256")


def test_mcp_client_urls_credentials_and_cleanup(live_mcp_contract):
    import asyncio
    import json

    import httpx

    transport, oauth = live_mcp_contract
    seen = []

    async def scenario():
        async def endpoint(request):
            claims = oauth._authenticate_token(
                request.headers["authorization"].split()[1], "weather:read"
            )
            seen.append((request.url.path, claims["tenant_id"]))
            await asyncio.sleep(0)
            if request.method == "GET":
                return httpx.Response(200, json={"tools": [{"name": "weather"}]})
            assert json.loads(request.content)["arguments"]["tenant_id"] == claims["tenant_id"]
            return httpx.Response(200, json={"content": [{"type": "text", "text": "{}"}]})

        client = transport.MCPClient({"weather": "http://weather:8000/mcp/v1"}, token="opaque")
        pooled = httpx.AsyncClient(
            base_url=client.servers["weather"], transport=httpx.MockTransport(endpoint)
        )
        client._clients["weather"] = pooled
        assert client.token is None
        with pytest.raises(transport.MCPAuthenticationError):
            await client.list_tools("weather")

        async def request(tenant):
            token = _caller_token(tenant)
            with client.bind_credentials(token, tenant):
                assert client.token == token
                assert await client.list_tools("weather") == [{"name": "weather"}]
                await client.call_tool("weather", "weather", {})
                with pytest.raises(transport.MCPAuthenticationError):
                    await client.call_tool("weather", "weather", {"tenant_id": "someone-else"})
            assert client.token is None

        await asyncio.gather(request("tenant-a"), request("tenant-b"))
        with client.bind_credentials(_caller_token(exp=1), "tenant-a"):
            # Discovery must reauthenticate, even when the tools were seen before.
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as expired:
                await client.list_tools("weather")
            assert expired.value.status_code == 401
        await client.close()
        assert pooled.is_closed
        assert not client._clients

    asyncio.run(scenario())
    assert sorted(seen) == sorted(
        [
            ("/v1/mcp/tools", "tenant-a"),
            ("/v1/mcp/tools", "tenant-b"),
            ("/v1/mcp/tools/call", "tenant-a"),
            ("/v1/mcp/tools/call", "tenant-b"),
        ]
    )


def test_mcp_http200_tool_error_is_failure(live_mcp_contract):
    import asyncio

    import httpx

    transport, _ = live_mcp_contract

    async def scenario():
        def endpoint(request):
            return httpx.Response(
                200,
                json={
                    "isError": True,
                    "content": [{"type": "text", "text": "private vendor details"}],
                },
            )

        client = transport.MCPClient({"market": "http://market:8000"})
        client._clients["market"] = httpx.AsyncClient(
            base_url=client.servers["market"], transport=httpx.MockTransport(endpoint)
        )
        with client.bind_credentials(_caller_token(scope="market:read"), "tenant-a"):
            result = await client.call_tools_parallel(
                [{"server": "market", "tool": "get_market_price"}]
            )
        assert result == [
            {
                "server": "market",
                "tool": "get_market_price",
                "error": "tool_call_failed",
                "error_type": "tool_error",
                "status": "failed",
            }
        ]
        import circuit_breaker

        assert circuit_breaker.mcp_breakers.get("market").status()["failures"] == 1
        await client.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [[], {"isError": "false"}, {"error": "db_down"}])
def test_mcp_malformed_success_cannot_be_consumed(live_mcp_contract, payload):
    import httpx

    transport, _ = live_mcp_contract
    response = httpx.Response(200, json=payload, request=httpx.Request("POST", "http://mcp"))
    with pytest.raises(transport.MCPError):
        transport.MCPClient._response_payload(response)


@pytest.mark.parametrize(
    "tenant,scope,status",
    [
        ("tenant-a", "weather:read", 200),
        ("tenant-a", "market:read", 403),
        (None, "weather:read", 401),
        ("invalid tenant", "weather:read", 400),
        (42, "weather:read", 400),
        ("tenant-a", ["weather:read"], 403),
    ],
)
def test_mcp_auth_scope_tenant_boundaries(live_mcp_contract, tenant, scope, status):
    from fastapi import HTTPException

    _, oauth = live_mcp_contract
    if status == 200:
        assert (
            oauth._authenticate_token(_caller_token(tenant, scope), "weather:read")["tenant_id"]
            == tenant
        )
    else:
        with pytest.raises(HTTPException) as rejected:
            oauth._authenticate_token(_caller_token(tenant, scope), "weather:read")
        assert rejected.value.status_code == status


def test_mcp_production_rs256_and_algorithm_confusion(live_mcp_contract, monkeypatch):
    import time

    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import HTTPException

    _, oauth = live_mcp_contract
    monkeypatch.setenv("SAHOOL_ENV", "production")
    with pytest.raises(HTTPException) as no_key:
        oauth._authenticate_token(_caller_token(), "weather:read")
    assert no_key.value.status_code == 503
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    monkeypatch.setenv("JWT_PUBLIC_KEY", public.decode())
    monkeypatch.delenv("JWT_SECRET")
    token = jwt.encode(
        {
            "sub": "42",
            "tenant_id": "tenant-a",
            "scope": "weather:read",
            "iss": "sahool-auth",
            "aud": "sahool",
            "exp": int(time.time()) + 300,
        },
        key,
        algorithm="RS256",
    )
    assert oauth._authenticate_token(token, "weather:read")["tenant_id"] == "tenant-a"
    with pytest.raises(HTTPException) as confused:
        oauth._authenticate_token(_caller_token(), "weather:read")
    assert confused.value.status_code == 401


@pytest.mark.parametrize(
    "module_name,scope",
    [
        ("sentinel_hub_server", "satellite:read"),
        ("weather_server", "weather:read"),
        ("wofost_server", "crop:read"),
        ("market_server", "market:read"),
    ],
)
def test_supervisor_discovers_each_real_mcp_app(live_mcp_contract, module_name, scope):
    import asyncio

    import httpx

    transport, _ = live_mcp_contract
    module = _load("_live_" + module_name, MCP / (module_name + ".py"))

    async def scenario():
        client = transport.MCPClient({module_name: "http://mcp"})
        client._clients[module_name] = httpx.AsyncClient(
            base_url="http://mcp", transport=httpx.ASGITransport(app=module.app)
        )
        with client.bind_credentials(_caller_token(scope=scope), "tenant-a"):
            tools = await client.list_tools(module_name)
        assert tools and all(tool.get("name") for tool in tools)
        with client.bind_credentials(_caller_token(scope="unrelated:read"), "tenant-a"):
            with pytest.raises(httpx.HTTPStatusError) as denied:
                await client.list_tools(module_name)
            assert denied.value.response.status_code == 403
        await client.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "module_name,scope",
    [
        ("sentinel_hub_server", "satellite:read"),
        ("weather_server", "weather:read"),
        ("wofost_server", "crop:read"),
    ],
)
def test_mcp_idempotency_cannot_cross_callers(live_mcp_contract, monkeypatch, module_name, scope):
    module = _load("_live_" + module_name, MCP / (module_name + ".py"))
    monkeypatch.setattr(module, "IDEMPOTENCY_CACHE", {})
    calls = []

    async def execute(*args):
        calls.append(args)
        return {"content": [{"type": "text", "text": str(len(calls))}]}

    monkeypatch.setattr(
        module, "_execute_tool" if module_name == "sentinel_hub_server" else "_execute", execute
    )
    client = TestClient(module.app)
    body = {"name": "probe", "arguments": {"lat": 1}, "request_id": "shared-key"}
    tokens = [
        _caller_token("tenant-a", scope),
        _caller_token("tenant-b", scope),
        _caller_token("tenant-a", scope, sub="43"),
    ]
    results = [
        client.post("/v1/mcp/tools/call", json=body, headers={"Authorization": "Bearer " + token})
        for token in tokens
    ]
    assert [response.status_code for response in results] == [200, 200, 200]
    assert len(calls) == 3
    assert len({response.text for response in results}) == 3
    repeated = client.post(
        "/v1/mcp/tools/call", json=body, headers={"Authorization": "Bearer " + tokens[0]}
    )
    assert repeated.json() == results[0].json() and len(calls) == 3
    body["arguments"]["lat"] = 2
    client.post("/v1/mcp/tools/call", json=body, headers={"Authorization": "Bearer " + tokens[0]})
    assert len(calls) == 4


def test_compose_starts_each_distinct_mcp_module():
    import yaml

    services = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))[
        "services"
    ]
    modules = {
        "sentinel-hub": "sentinel_hub_server",
        "weather": "weather_server",
        "wofost": "wofost_server",
        "market": "market_server",
    }
    supervisor = services["sahool-supervisor-agent"]["environment"]
    assert services["sahool-auth"]["environment"]["SAHOOL_ENV"] == supervisor["SAHOOL_ENV"]
    for name, module in modules.items():
        env = services[f"sahool-{name}-mcp"]["environment"]
        assert env["MCP_SERVER_MODULE"] == module
        assert env["JWT_PUBLIC_KEY"] == supervisor["JWT_PUBLIC_KEY"]
        assert env["SAHOOL_ENV"] == supervisor["SAHOOL_ENV"]
        key = "MCP_" + name.upper().replace("-", "_") + "_URL"
        assert supervisor[key] == f"http://sahool-{name}-mcp:8000"


def test_market_read_scope_cannot_create_contract(live_mcp_contract, monkeypatch):
    module = _load("_live_market_server", MCP / "market_server.py")

    async def must_not_run(args):
        pytest.fail("read scope reached a market write")

    monkeypatch.setattr(module, "tool_create_forward_contract", must_not_run)
    response = TestClient(module.app).post(
        "/v1/mcp/tools/call",
        json={"name": "create_forward_contract"},
        headers={"Authorization": "Bearer " + _caller_token(scope="market:read")},
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "row",
    [
        None,
        {"avg_price": None, "observed_date": None, "sample_count": 0},
        {"avg_price": 0, "observed_date": "2026-09-01", "sample_count": 1},
        {"avg_price": float("nan"), "observed_date": "2026-09-01", "sample_count": 1},
    ],
)
def test_market_no_observation_cannot_become_zero_price(live_mcp_contract, monkeypatch, row):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from fastapi import HTTPException

    module = _load("_live_market_server", MCP / "market_server.py")

    async def fetchrow(*args):
        return row

    @asynccontextmanager
    async def connection(tenant):
        assert tenant == "tenant-a"
        yield SimpleNamespace(fetchrow=fetchrow)

    monkeypatch.setattr(module, "tenant_connection", connection)
    with pytest.raises(HTTPException) as unavailable:
        asyncio.run(module.tool_get_market_price({"tenant_id": "tenant-a"}))
    assert unavailable.value.status_code == 424


def test_market_price_preserves_observation_currency_date_and_unknown_unit(
    live_mcp_contract, monkeypatch
):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    module = _load("_live_market_server", MCP / "market_server.py")

    async def fetchrow(sql, crop, market):
        assert "currency='USD'" in sql
        assert "recorded_date <= CURRENT_DATE" in sql
        return {"avg_price": 3.25, "observed_date": "2026-09-01", "sample_count": 2}

    @asynccontextmanager
    async def connection(tenant):
        yield SimpleNamespace(fetchrow=fetchrow)

    monkeypatch.setattr(module, "tenant_connection", connection)
    result = asyncio.run(module.tool_get_market_price({"tenant_id": "tenant-a"}))
    assert result == {
        "price_usd": 3.25,
        "currency": "USD",
        "unit": None,
        "updated": "2026-09-01",
        "sample_count": 2,
        "aggregation": "mean_last_7_days",
    }


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"recorded_date": "2026-09-01", "price_usd": 3.25}],
        [
            {"recorded_date": "2026-09-01", "price_usd": 4},
            {"recorded_date": "2026-08-20", "price_usd": 2},
        ],
    ],
)
def test_market_history_does_not_claim_a_forecast(live_mcp_contract, monkeypatch, rows):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from fastapi import HTTPException

    module = _load("_live_market_server", MCP / "market_server.py")

    async def fetch(sql, crop, market):
        assert "market_location=$2" in sql and "GROUP BY recorded_date" in sql
        return rows

    @asynccontextmanager
    async def connection(tenant):
        yield SimpleNamespace(fetch=fetch)

    monkeypatch.setattr(module, "tenant_connection", connection)
    if not rows:
        with pytest.raises(HTTPException) as unavailable:
            asyncio.run(module.tool_get_price_trend({"tenant_id": "tenant-a"}))
        assert unavailable.value.status_code == 424
        return
    result = asyncio.run(module.tool_get_price_trend({"tenant_id": "tenant-a"}))
    assert "forecast" not in result and "current_price" not in result
    assert result["currency"] == "USD" and result["unit"] is None
    assert result["current_price_usd"] == rows[0]["price_usd"]
    assert result["historical_change_pct"] == (100 if len(rows) == 2 else None)
    assert result["observation_count"] == len(rows)


def test_mcp_tool_transport_failure_is_not_replayed(live_mcp_contract):
    import asyncio

    import httpx

    transport, _ = live_mcp_contract
    calls = []

    async def scenario():
        def endpoint(request):
            calls.append(request)
            raise httpx.ReadTimeout("reply lost after commit")

        client = transport.MCPClient({"market": "http://market"})
        client._clients["market"] = httpx.AsyncClient(
            base_url="http://market", transport=httpx.MockTransport(endpoint)
        )
        with client.bind_credentials(_caller_token(scope="market:read market:write"), "tenant-a"):
            with pytest.raises(httpx.ReadTimeout):
                await client.call_tool(
                    "market", "market_create_procurement", {}, request_id="request-1"
                )
        await client.close()

    asyncio.run(scenario())
    assert len(calls) == 1
