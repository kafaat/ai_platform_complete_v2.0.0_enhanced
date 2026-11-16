"""W0-05 (findings fields-5 / routes-5): the shared service token no longer chooses the tenant.

``/internal/fields/{id}/state`` and ``/internal/events/ai-advice`` used to take ``tenant_id``
from the query or body behind ``SAHOOL_AGENT_TOKEN`` alone, which about twenty services hold.
Now the caller must also present ``X-Tenant-Assertion`` (shared.security.service_tenant_assertion)
signed with ``PLATFORM_TENANT_ASSERTION_KEY`` for exactly that tenant, request and path, and be
in the caller allowlist. Negative control: before the change, each 401/403 case below was a 404
from the stubbed field check, i.e. the request reached the tenant's data.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from shared.security.tenant_assertion_headers import tenant_assertion_headers

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
TOKEN = "unit-service-token-value"
KEY = "w0-05-platform-assertion-key-0123456789"
TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
STATE_PATH = "/internal/fields/fld_1/state"
ADVICE_PATH = "/internal/events/ai-advice"


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


@pytest.fixture()
def client(app_mod, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("PLATFORM_TENANT_ASSERTION_KEY", KEY)
    monkeypatch.delenv("PLATFORM_INTERNAL_ALLOWED_CALLERS", raising=False)
    monkeypatch.delenv("PLATFORM_TENANT_ASSERTION_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")

    seen: list[str] = []

    @asynccontextmanager
    async def connection(user):
        seen.append(str(user.tenant_id))
        yield object()

    # Store-level stubs: a request that passes the assertion reaches the field check, which
    # answers 404 — that 404 is the proof the request got past the tenant gate.
    monkeypatch.setattr(app_mod, "tenant_connection", connection)
    monkeypatch.setattr(
        app_mod, "_assert_field_in_tenant", AsyncMock(side_effect=HTTPException(404, "nf"))
    )
    # No `with`: the app's lifespan (database start-up retries) is not what this file measures.
    c = TestClient(app_mod.app, raise_server_exceptions=False)
    c.seen_tenants = seen
    yield c


def _signed(tenant: str, path: str, method: str, service: str = "supervisor-agent", key=KEY):
    return tenant_assertion_headers(
        key=key, key_id="current", service=service, tenant_id=tenant, method=method, path=path
    )


def _state(client, headers):
    return client.get(STATE_PATH, params={"tenant_id": TENANT_A}, headers=headers)


def test_valid_token_and_query_tenant_without_assertion_is_401(client):
    r = _state(client, {"X-Agent-Token": TOKEN})
    assert r.status_code == 401, r.text
    assert client.seen_tenants == [], "no tenant connection may open before the assertion"


def test_assertion_for_another_tenant_is_403(client):
    headers = {"X-Agent-Token": TOKEN, **_signed(TENANT_B, STATE_PATH, "GET")}
    r = _state(client, headers)
    assert r.status_code == 403, r.text
    assert client.seen_tenants == [], "tenant A data was reached with an assertion for B"


def test_caller_outside_allowlist_is_403(client):
    headers = {"X-Agent-Token": TOKEN, **_signed(TENANT_A, STATE_PATH, "GET", service="raster")}
    r = _state(client, headers)
    assert r.status_code == 403, r.text
    assert "caller_not_allowed" in r.text, r.text


def test_assertion_for_another_path_or_key_is_403(client):
    other_path = {"X-Agent-Token": TOKEN, **_signed(TENANT_A, "/internal/fields/f2/state", "GET")}
    assert _state(client, other_path).status_code == 403, "assertion replayed on another field"
    wrong_key = {"X-Agent-Token": TOKEN, **_signed(TENANT_A, STATE_PATH, "GET", key="x" * 40)}
    assert _state(client, wrong_key).status_code == 403, "assertion signed with an unknown key"


def test_missing_key_fails_closed_503(client, monkeypatch):
    monkeypatch.delenv("PLATFORM_TENANT_ASSERTION_KEY")
    headers = {"X-Agent-Token": TOKEN, **_signed(TENANT_A, STATE_PATH, "GET")}
    r = _state(client, headers)
    assert r.status_code == 503, r.text


def test_service_token_still_checked_first(client):
    r = _state(client, _signed(TENANT_A, STATE_PATH, "GET"))
    assert r.status_code == 403, f"no service token must stay 403, got {r.status_code}"


def test_valid_assertion_reaches_the_tenant_scope(client):
    headers = {"X-Agent-Token": TOKEN, **_signed(TENANT_A, STATE_PATH, "GET")}
    r = _state(client, headers)
    assert r.status_code == 404, r.text  # the stubbed field check, past the gate
    assert client.seen_tenants == [TENANT_A], client.seen_tenants


def test_ai_advice_without_assertion_is_401_and_wrong_tenant_403(client):
    body = {"tenant_id": TENANT_A, "field_id": "fld_1", "question": "q"}
    r = client.post(ADVICE_PATH, json=body, headers={"X-Agent-Token": TOKEN})
    assert r.status_code == 401, r.text
    signed_b = _signed(TENANT_B, ADVICE_PATH, "POST", service="ai_agronomist")
    r = client.post(ADVICE_PATH, json=body, headers={"X-Agent-Token": TOKEN, **signed_b})
    assert r.status_code == 403, r.text
    assert client.seen_tenants == [], "the advice event reached a tenant without a valid claim"
    signed_a = _signed(TENANT_A, ADVICE_PATH, "POST", service="ai_agronomist")
    r = client.post(ADVICE_PATH, json=body, headers={"X-Agent-Token": TOKEN, **signed_a})
    assert r.status_code == 404, r.text
    assert client.seen_tenants == [TENANT_A], client.seen_tenants


def test_replay_is_refused_and_production_requires_a_replay_store(app_mod, monkeypatch):
    from api.service_token_auth import PLATFORM_INTERNAL, verify_request_tenant

    monkeypatch.setenv("PLATFORM_TENANT_ASSERTION_KEY", KEY)
    signed = _signed(TENANT_A, STATE_PATH, "GET")
    headers = {k.lower(): v for k, v in signed.items()}
    used: set[str] = set()

    def claim_once(key):
        if key in used:
            raise HTTPException(403, "tenant_assertion_replayed")
        used.add(key)

    kwargs = {"method": "GET", "path": STATE_PATH, "headers": headers, "tenant_id": TENANT_A}
    assert verify_request_tenant(PLATFORM_INTERNAL, claim_once=claim_once, **kwargs) == TENANT_A
    with pytest.raises(HTTPException) as replay:
        verify_request_tenant(PLATFORM_INTERNAL, claim_once=claim_once, **kwargs)
    assert replay.value.status_code == 403, replay.value.detail

    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.delenv("PLATFORM_TENANT_ASSERTION_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(HTTPException) as no_store:
        verify_request_tenant(PLATFORM_INTERNAL, **{**kwargs, "headers": headers})
    assert no_store.value.status_code == 503, no_store.value.detail


@pytest.mark.asyncio
async def test_ai_agronomist_signs_the_tenant_it_verified(monkeypatch):
    import httpx

    from services.ai_agronomist import ai_evidence_runtime as runtime
    from shared.security.service_tenant_assertion import verify_tenant_assertion

    monkeypatch.setattr(runtime, "AGENT_TOKEN", "unit-credential")
    monkeypatch.setenv("PLATFORM_TENANT_ASSERTION_KEY", KEY)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"persisted": True})

    client_cls = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client_cls(transport=transport, **kw))
    event = await runtime._record_ai_advice_event(
        tenant_id=TENANT_A,
        field_id="fld_1",
        question="q",
        evidence_ids=[],
        confidence=0.1,
        selected_imagery_date=None,
        endpoint_mode="chat",
    )
    assert event["status"] == "recorded", event
    request = seen[0]
    claims = verify_tenant_assertion(
        request.headers["X-Tenant-Assertion"],
        {"current": KEY},
        "ai_agronomist",
        TENANT_A,
        expected_method="POST",
        expected_path=ADVICE_PATH,
        expected_request_id=request.headers["X-Request-Id"],
    )
    assert claims.tenant_id == TENANT_A, claims

    monkeypatch.delenv("PLATFORM_TENANT_ASSERTION_KEY")
    seen.clear()
    skipped = await runtime._record_ai_advice_event(
        tenant_id=TENANT_A,
        field_id="fld_1",
        question="q",
        evidence_ids=[],
        confidence=0.1,
        selected_imagery_date=None,
        endpoint_mode="chat",
    )
    assert skipped["status"] == "skipped", skipped
    assert seen == [], "an unsigned advice event was sent"


# ── W0-07: /v1/edge/sync in service mode (the edge-inference channel, its own key) ──────────
EDGE_KEY = "w0-07-edge-assertion-key-0123456789abcdef"


def _edge_request(headers: dict[str, str]):
    from starlette.requests import Request

    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/edge/sync",
        "raw_path": b"/v1/edge/sync",
        "headers": raw,
        "query_string": b"",
    }
    return Request(scope)


def _edge_signed(tenant: str, service: str = "edge-inference", key: str = EDGE_KEY):
    return tenant_assertion_headers(
        key=key,
        key_id="current",
        service=service,
        tenant_id=tenant,
        method="POST",
        path="/v1/edge/sync",
    )


def test_edge_sync_service_mode_writes_for_the_signed_tenant_only(app_mod, monkeypatch):
    from api.routers.edge import edge_sync_actor

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("EDGE_TENANT_ASSERTION_KEY", EDGE_KEY)
    monkeypatch.delenv("EDGE_SYNC_ALLOWED_CALLERS", raising=False)
    monkeypatch.delenv("PLATFORM_TENANT_ASSERTION_REDIS_URL", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")

    ok = edge_sync_actor(_edge_request({"X-Agent-Token": TOKEN, **_edge_signed(TENANT_B)}))
    assert str(ok.tenant_id) == TENANT_B, ok
    assert ok.user_id == "service:edge-inference", ok

    swapped = {"X-Agent-Token": TOKEN, **_edge_signed(TENANT_A), "X-Tenant-Id": TENANT_B}
    with pytest.raises(HTTPException) as exc:
        edge_sync_actor(_edge_request(swapped))
    assert exc.value.status_code == 403, exc.value.detail

    # The platform-internal key does not open the edge channel, and vice versa.
    with pytest.raises(HTTPException) as other_key:
        edge_sync_actor(_edge_request({"X-Agent-Token": TOKEN, **_edge_signed(TENANT_B, key=KEY)}))
    assert other_key.value.status_code == 403, other_key.value.detail

    with pytest.raises(HTTPException) as stranger:
        edge_sync_actor(
            _edge_request({"X-Agent-Token": TOKEN, **_edge_signed(TENANT_B, service="raster")})
        )
    assert stranger.value.status_code == 403, stranger.value.detail

    with pytest.raises(HTTPException) as no_token:
        edge_sync_actor(_edge_request(_edge_signed(TENANT_B)))
    assert no_token.value.status_code == 403, "service mode without the service token"


def test_edge_sync_without_service_headers_still_needs_a_bearer(app_mod):
    from api.routers.edge import edge_sync_actor

    with pytest.raises(HTTPException) as exc:
        edge_sync_actor(_edge_request({}), authorization=None)
    assert exc.value.status_code == 401, exc.value.detail
