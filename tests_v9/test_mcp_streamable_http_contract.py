"""MCP HTTP lifecycle and identity regression against the real ASGI adapter.

No sockets or external services: real FastAPI + HTTPX ASGITransport and JWT scope
verification; only the downstream business tool is a controlled in-process route.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

import httpx
import jwt
import pytest
from fastapi import Depends, FastAPI, HTTPException, Request

pytestmark = [pytest.mark.unit, pytest.mark.mcp]
ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "services/mcp_servers"
SECRET = "mcp-transport-test-key-not-for-production-1234"
VERSION = "2025-06-18"
PATH = "/mcp/v1/stream"


def _load(name, path, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def adapter(monkeypatch):
    import shared

    monkeypatch.setattr(shared, "__path__", [str(ROOT / "shared"), str(MCP / "shared")])
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("SAHOOL_ALLOW_HS256_IN_PROD", raising=False)
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://approved.example")
    oauth = _load("shared.oauth_middleware", MCP / "shared/oauth_middleware.py", monkeypatch)
    module = _load("shared.streamable_http", MCP / "shared/streamable_http.py", monkeypatch)
    app = FastAPI(title="Controlled MCP tool", version="1.0")
    calls = []
    state = {"delay": 0, "status": 200, "response": None, "inner_scope": "weather:read"}

    async def inner_user(request: Request):
        claims = oauth._authenticate_token(
            request.headers["authorization"].split(" ", 1)[1], state["inner_scope"]
        )
        return claims

    @app.get("/v1/mcp/tools")
    async def tools(user: dict = Depends(inner_user)):
        return {"tools": [{"name": "read_weather"}, {"name": "write_valve"}]}

    @app.post("/v1/mcp/tools/call")
    async def call(request: Request, user: dict = Depends(inner_user)):
        body = await request.json()
        calls.append((user, body, dict(request.headers)))
        if state["delay"]:
            await asyncio.sleep(state["delay"])
        if state["status"] != 200:
            raise HTTPException(state["status"], "secret upstream error must not leak")
        if state["response"] is not None:
            return state["response"]
        return {"tenant_id": user["tenant_id"], "value": 12.5, "verified": False}

    transport = module.StreamableHTTPTransport(
        app,
        required_scope="weather:read",
        allowed_tools=frozenset({"read_weather"}),
        timeout_seconds=0.2,
    )
    return app, calls, state, transport


def headers(tenant="tenant-a", scope="weather:read", **claims):
    payload = {
        "sub": "user-1",
        "tenant_id": tenant,
        "iss": "sahool-auth",
        "aud": "sahool",
        "scope": scope,
        "exp": int(time.time()) + 300,
        **claims,
    }
    return {
        "Authorization": "Bearer " + jwt.encode(payload, SECRET, algorithm="HS256"),
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": VERSION,
    }


def rpc(method="tools/call", params=None, request_id=1):
    result = {"jsonrpc": "2.0", "method": method, "id": request_id}
    if params is not None:
        result["params"] = params
    elif method == "tools/call":
        result["params"] = {"name": "read_weather", "arguments": {"field_id": "field-a"}}
    return result


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.example")


@pytest.mark.asyncio
async def test_initialize_notification_list_and_call_preserve_real_caller(adapter):
    app, calls, state, transport = adapter
    async with client(app) as ac:
        init_headers = headers()
        init_headers.pop("MCP-Protocol-Version")
        initialized = await ac.post(
            PATH,
            json=rpc(
                "initialize",
                {
                    "protocolVersion": VERSION,
                    "clientInfo": {"name": "voice-bridge", "version": "1.0"},
                    "capabilities": {},
                },
            ),
            headers=init_headers,
        )
        assert initialized.status_code == 200
        assert initialized.json()["result"]["protocolVersion"] == VERSION
        assert initialized.json()["result"]["capabilities"] == {"tools": {"listChanged": False}}
        assert "mcp-session-id" not in initialized.headers
        notification = await ac.post(
            PATH,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=headers(),
        )
        assert notification.status_code == 202 and notification.content == b""
        listed = await ac.post(PATH, json=rpc("tools/list"), headers=headers())
        assert listed.json()["result"]["tools"] == [
            {"name": "read_weather", "inputSchema": {"type": "object"}}
        ]
        auth = headers()
        auth["X-Tenant-Id"] = "forged-tenant"
        auth["X-Agent-Token"] = "do-not-forward"
        called = await ac.post(PATH, json=rpc(), headers=auth)
        assert called.status_code == 200
        assert called.headers["cache-control"] == "no-store"
        result = called.json()["result"]
        assert result["structuredContent"] == {
            "tenant_id": "tenant-a",
            "value": 12.5,
            "verified": False,
        }
        assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
        assert not result["isError"]
    assert len(calls) == 1
    claims, body, forwarded = calls[0]
    assert claims["tenant_id"] == body["arguments"]["tenant_id"] == "tenant-a"
    assert forwarded["authorization"] == auth["Authorization"]
    assert "x-tenant-id" not in forwarded and "x-agent-token" not in forwarded
    assert "request_id" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,status", [("missing", 401), ("scope", 403), ("expired", 401), ("issuer", 401)]
)
async def test_authentication_precedes_body_decoding(adapter, case, status):
    app, calls, _, _ = adapter
    auth = headers()
    if case == "missing":
        auth.pop("Authorization")
    elif case == "scope":
        auth = headers(scope="crop:read")
    elif case == "expired":
        auth = headers(exp=1)
    elif case == "issuer":
        auth = headers(iss="untrusted")
    async with client(app) as ac:
        response = await ac.post(PATH, content=b'{"secret":', headers=auth)
    assert response.status_code == status
    assert calls == []


@pytest.mark.asyncio
async def test_caller_cannot_select_other_tenant_or_hidden_write_tool(adapter):
    app, calls, _, _ = adapter
    async with client(app) as ac:
        for params in (
            {"name": "read_weather", "arguments": {"tenant_id": "tenant-b"}},
            {"name": "write_valve", "arguments": {}},
        ):
            response = await ac.post(PATH, json=rpc(params=params), headers=headers(scope="admin"))
            assert response.json()["error"]["code"] == -32602
    assert calls == []


@pytest.mark.asyncio
async def test_concurrent_tenants_do_not_share_credentials(adapter):
    app, calls, _, _ = adapter
    async with client(app) as ac:
        responses = await asyncio.gather(
            *(
                ac.post(PATH, json=rpc(request_id=tenant), headers=headers(tenant=tenant))
                for tenant in ("tenant-a", "tenant-b")
            )
        )
    assert [r.json()["result"]["structuredContent"]["tenant_id"] for r in responses] == [
        "tenant-a",
        "tenant-b",
    ]
    assert all(user["tenant_id"] == body["arguments"]["tenant_id"] for user, body, _ in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404, 422, 500, 503])
async def test_inner_http_failure_cannot_be_reported_as_success(adapter, status):
    app, calls, state, _ = adapter
    state["status"] = status
    async with client(app) as ac:
        response = await ac.post(PATH, json=rpc(), headers=headers())
    assert "error" in response.json() and "result" not in response.json()
    assert "secret" not in response.text
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_inner_scope_is_still_enforced(adapter):
    app, calls, state, _ = adapter
    state["inner_scope"] = "crop:read"
    async with client(app) as ac:
        response = await ac.post(PATH, json=rpc(), headers=headers())
    assert "error" in response.json() and calls == []


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_not_retried(adapter):
    app, calls, state, _ = adapter
    state["delay"] = 2
    start = time.monotonic()
    async with client(app) as ac:
        response = await ac.post(PATH, json=rpc(), headers=headers())
    assert time.monotonic() - start < 1.5
    assert response.json()["error"]["code"] == -32000
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [[], None, "text", {"jsonrpc": "1.0"}, {"jsonrpc": "2.0", "method": "ping", "id": True}]
)
async def test_invalid_jsonrpc_shapes_are_client_errors(adapter, body):
    app, calls, _, _ = adapter
    async with client(app) as ac:
        response = await ac.post(PATH, content=json.dumps(body), headers=headers())
    assert response.status_code == 400 and response.json()["error"]["code"] == -32600
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b'{"x":', b'{"x":NaN}', b"\xff"])
async def test_invalid_json_is_parse_error(adapter, body):
    async with client(adapter[0]) as ac:
        response = await ac.post(PATH, content=body, headers=headers())
    assert response.status_code == 400 and response.json()["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_notifications_never_execute_tool_or_return_jsonrpc_reply(adapter):
    app, calls, _, _ = adapter
    async with client(app) as ac:
        body = rpc()
        body.pop("id")
        no_id = await ac.post(PATH, json=body, headers=headers())
        assert no_id.status_code == 400
        unknown = await ac.post(
            PATH, json={"jsonrpc": "2.0", "method": "notifications/unknown"}, headers=headers()
        )
        assert unknown.status_code == 202 and unknown.content == b""
    assert calls == []


@pytest.mark.asyncio
async def test_version_negotiation_is_explicit_and_modern_envelope_is_not_claimed(adapter):
    async with client(adapter[0]) as ac:
        init_headers = headers()
        init_headers.pop("MCP-Protocol-Version")
        init = await ac.post(
            PATH,
            json=rpc(
                "initialize",
                {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {},
                    "clientInfo": {"name": "client", "version": "1"},
                },
            ),
            headers=init_headers,
        )
        assert init.json()["result"]["protocolVersion"] == VERSION
        for value in (None, "2026-07-28", "2024-11-05"):
            request_headers = headers()
            if value is None:
                request_headers.pop("MCP-Protocol-Version")
            else:
                request_headers["MCP-Protocol-Version"] = value
            response = await ac.post(PATH, json=rpc("tools/list"), headers=request_headers)
            assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin,expected",
    [
        ("https://approved.example", 200),
        ("https://evil.example", 403),
        ("null", 403),
        ("https://approved.example.evil", 403),
    ],
)
async def test_origins_are_exact_operator_allowlist_not_host(adapter, origin, expected):
    auth = {**headers(), "Origin": origin, "Host": origin.removeprefix("https://")}
    async with client(adapter[0]) as ac:
        response = await ac.post(PATH, json=rpc("ping"), headers=auth)
        get = await ac.get(PATH, headers=auth)
    assert response.status_code == expected
    assert get.status_code == (405 if expected == 200 else 403)


@pytest.mark.asyncio
async def test_body_limit_accept_content_type_and_single_page(adapter):
    async with client(adapter[0]) as ac:
        oversized = await ac.post(PATH, content=b" " * 65537, headers=headers())
        assert oversized.status_code == 413
        for accept in ("*/*", "application/json", "application/json, text/event-stream;q=0"):
            response = await ac.post(
                PATH, json=rpc("ping"), headers={**headers(), "Accept": accept}
            )
            assert response.status_code == 406
        accepted = await ac.post(
            PATH,
            json=rpc("ping"),
            headers={**headers(), "Accept": "application/json;q=0.5, text/event-stream;q=0.2"},
        )
        assert accepted.json()["result"] == {}
        wrong_type = await ac.post(
            PATH, content="{}", headers={**headers(), "Content-Type": "text/plain"}
        )
        assert wrong_type.status_code == 415
        cursor = await ac.post(
            PATH, json=rpc("tools/list", {"cursor": "not-issued"}), headers=headers()
        )
        assert cursor.json()["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_application_tool_error_is_preserved(adapter):
    app, _, state, _ = adapter
    state["response"] = {"isError": True, "content": [{"type": "text", "text": "unavailable"}]}
    async with client(app) as ac:
        response = await ac.post(PATH, json=rpc(), headers=headers())
    assert response.json()["result"]["isError"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "server,scope",
    [
        ("weather_server", "weather:read"),
        ("wofost_server", "crop:read"),
        ("sentinel_hub_server", "satellite:read"),
    ],
)
async def test_real_service_registration_authenticates_discovery(
    adapter, monkeypatch, server, scope
):
    monkeypatch.syspath_prepend(str(MCP))
    module = _load(f"_transport_test_{server}", MCP / f"{server}.py", monkeypatch)
    async with client(module.app) as ac:
        allowed = await ac.post(PATH, json=rpc("tools/list"), headers=headers(scope=scope))
        assert allowed.status_code == 200 and allowed.json()["result"]["tools"]
        denied = await ac.post(PATH, json=rpc("tools/list"), headers=headers(scope="wrong:read"))
        assert denied.status_code == 403


@pytest.mark.asyncio
async def test_real_market_surface_exports_only_price_reads(adapter, monkeypatch):
    monkeypatch.syspath_prepend(str(MCP))
    module = _load("_transport_test_market", MCP / "market_server.py", monkeypatch)
    seen = []

    async def price(arguments):
        seen.append(arguments)
        return {"tenant_id": arguments["tenant_id"], "price_usd": 10, "source": "controlled-test"}

    monkeypatch.setattr(module, "tool_get_market_price", price)
    async with client(module.app) as ac:
        auth = headers(scope="admin")
        listing = await ac.post(PATH, json=rpc("tools/list"), headers=auth)
        names = {item["name"] for item in listing.json()["result"]["tools"]}
        assert names == {"get_market_price", "get_price_trend"}
        for name in module._MARKET_WRITE_TOOLS:
            denied = await ac.post(PATH, json=rpc(params={"name": name}), headers=auth)
            assert denied.json()["error"]["code"] == -32602
        called = await ac.post(PATH, json=rpc(params={"name": "get_market_price"}), headers=auth)
        assert called.json()["result"]["isError"] is False
    assert seen == [{"tenant_id": "tenant-a"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [json.dumps(rpc("ping")).encode("utf-16"), b'{"n":1e999}'])
async def test_only_finite_utf8_json_is_accepted(adapter, body):
    async with client(adapter[0]) as ac:
        response = await ac.post(PATH, content=body, headers=headers())
    assert response.status_code == 400 and response.json()["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_slow_request_body_is_bounded_before_dispatch(adapter):
    async def delayed_body():
        yield b'{"jsonrpc":'
        await asyncio.sleep(2)
        yield b'"2.0"}'

    async with client(adapter[0]) as ac:
        response = await ac.post(PATH, content=delayed_body(), headers=headers())
    assert response.status_code == 408
    assert adapter[1] == []


@pytest.mark.asyncio
async def test_jsonrpc_errors_do_not_reach_business_tool(adapter):
    async with client(adapter[0]) as ac:
        for body, code in (
            (rpc("unknown"), -32601),
            (rpc("tools/call", {"name": "read_weather", "arguments": []}), -32602),
            (rpc("initialize", {"protocolVersion": VERSION}), -32602),
        ):
            response = await ac.post(PATH, json=body, headers=headers())
            assert response.json()["error"]["code"] == code
    assert adapter[1] == []
