"""Canonical identity/field authority contracts for the realtime control plane."""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

# Load the uniquely named package without changing global import search paths.
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "services/realtime-session/realtime_session"
if "realtime_session" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "realtime_session", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["realtime_session"] = module
    spec.loader.exec_module(module)

from realtime_session import platform as platform_module  # noqa: E402
from realtime_session.contracts import Principal, SessionError  # noqa: E402
from realtime_session.platform import PlatformAuthority  # noqa: E402

ORIGIN = "http://sahool-platform:8000"
TOKEN = "synthetic-bearer-never-reflected"
TENANT = "00000000-0000-0000-0000-0000000000a1"
ME = {
    "tenant_id": TENANT,
    "user_id": 17,
    "ai_policy_envelope": {
        "tenant_id": TENANT,
        "contract": "sahool.ai_policy_envelope",
        "contract_version": 2,
        "allowed_tools": [],
    },
}


@pytest.mark.asyncio
async def test_identity_and_field_use_same_bearer_and_canonical_scoped_read():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == f"Bearer {TOKEN}", (
            "forward the supplied identity"
        )
        assert "X-Tenant-ID" not in request.headers, (
            "tenant authority is the verified platform identity"
        )
        return httpx.Response(
            200, json=ME if request.url.path.endswith("/me") else {"field_id": "f-17"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        authority = PlatformAuthority(ORIGIN, client)
        principal = await authority.identity(TOKEN)
        await authority.authorize_field(TOKEN, principal, "f-17")
    assert principal == Principal(TENANT, "17"), "normalize platform numeric user identities"
    assert [request.url.path for request in requests] == ["/api/v1/me", "/api/v1/fields/f-17"], (
        "reuse the canonical FIELD_VIEW/RLS read without another authorization model"
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.pop("ai_policy_envelope"),
        lambda p: p.update(user_id=True),
        lambda p: p.update(user_id=" "),
        lambda p: p.update(tenant_id=None),
        lambda p: p["ai_policy_envelope"].update(tenant_id="other-tenant"),
        lambda p: p["ai_policy_envelope"].update(contract="other.policy"),
        lambda p: p["ai_policy_envelope"].update(contract_version=1),
        lambda p: p["ai_policy_envelope"].update(contract_version=True),
        lambda p: p["ai_policy_envelope"].update(contract_version="2"),
        lambda p: p["ai_policy_envelope"].pop("allowed_tools"),
        lambda p: p["ai_policy_envelope"].update(allowed_tools=None),
        lambda p: p["ai_policy_envelope"].update(allowed_tools=[12]),
    ],
)
@pytest.mark.asyncio
async def test_missing_or_malformed_trusted_identity_fails_closed(change):
    payload = copy.deepcopy(ME)
    change(payload)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(SessionError) as failure:
            await PlatformAuthority(ORIGIN, client).identity(TOKEN)
    assert (failure.value.status, failure.value.code) == (403, "trusted_policy_required"), (
        "malformed platform identity/policy must never establish a realtime principal"
    )


@pytest.mark.parametrize("status", [401, 403, 404])
@pytest.mark.asyncio
async def test_upstream_denials_preserve_status_without_reflecting_sensitive_bodies(status):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, text=TOKEN))
    ) as client:
        with pytest.raises(SessionError) as failure:
            await PlatformAuthority(ORIGIN, client).authorize_field(
                TOKEN, Principal(TENANT, "17"), "other-field"
            )
    assert failure.value.status == status, (
        "preserve platform authentication/permission/ownership denials"
    )
    assert TOKEN not in str(failure.value), "never reflect upstream response bodies or credentials"


@pytest.mark.parametrize("status", [302, 307, 500, 503])
@pytest.mark.asyncio
async def test_redirects_and_failures_do_not_forward_bearer_to_another_origin(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={"Location": "https://other.example/token-sink"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        with pytest.raises(SessionError) as failure:
            await PlatformAuthority(ORIGIN, client).identity(TOKEN)
    assert failure.value.status == 503, "redirects are dependency failure, never identity responses"
    assert len(requests) == 1, (
        "override injected client redirect policy before credentials can leave the origin"
    )
    assert requests[0].url.host == "sahool-platform", (
        "only the configured authority receives the bearer"
    )


@pytest.mark.parametrize(
    "body", [b"not-json", b"[]", b'"scalar"', b'{"x":"' + b"x" * 65536 + b'"}']
)
@pytest.mark.asyncio
async def test_malformed_and_oversized_identity_responses_are_rejected(body):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(SessionError) as failure:
            await PlatformAuthority(ORIGIN, client).identity(TOKEN)
    assert (failure.value.status, failure.value.code) == (503, "platform_response_invalid"), (
        "a successful HTTP status cannot authorize malformed or excessive JSON"
    )


@pytest.mark.asyncio
async def test_timeout_is_sanitized_and_readiness_fails_closed():
    def handler(request):
        raise httpx.ReadTimeout(TOKEN, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        authority = PlatformAuthority(ORIGIN, client)
        with pytest.raises(SessionError) as failure:
            await authority.identity(TOKEN)
        assert await authority.ready() is False, (
            "unreachable platform cannot make the service ready"
        )
    assert (failure.value.status, failure.value.code) == (503, "platform_unavailable"), (
        "dependency timeouts must be bounded and sanitized"
    )
    assert TOKEN not in str(failure.value), (
        "transport error text may contain the request and must stay private"
    )


@pytest.mark.asyncio
async def test_slow_response_body_has_a_total_deadline_not_only_an_inactivity_timeout(monkeypatch):
    monkeypatch.setattr(platform_module, "_TOTAL_TIMEOUT_SECONDS", 0.05)
    observed = {"chunks": 0, "closed": False}

    class DrippingBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            for chunk in [b'{"x":"', *([b"x"] * 50), b'"}']:
                await asyncio.sleep(0.01)
                observed["chunks"] += 1
                yield chunk

        async def aclose(self):
            observed["closed"] = True

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=DrippingBody()))
    ) as client:
        with pytest.raises(SessionError) as failure:
            await PlatformAuthority(ORIGIN, client).identity(TOKEN)
    assert (failure.value.status, failure.value.code) == (503, "platform_unavailable"), (
        "continuously arriving bytes must not extend a platform request beyond its total deadline"
    )
    assert observed["chunks"] < 10, (
        "stop reading the body after the total deadline instead of consuming all chunks"
    )
    assert observed["closed"], "deadline cancellation must close the response stream"


@pytest.mark.asyncio
async def test_a_field_response_cannot_authorize_a_different_field():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"field_id": "wrong"}))
    ) as client:
        with pytest.raises(SessionError) as failure:
            await PlatformAuthority(ORIGIN, client).authorize_field(
                TOKEN, Principal(TENANT, "17"), "expected"
            )
    assert failure.value.code == "field_authorization_invalid", (
        "bind the successful read to the requested field"
    )


@pytest.mark.asyncio
async def test_field_id_cannot_change_endpoint_or_origin():
    field_id = "id?tenant=other#fragment"
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"field_id": field_id})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await PlatformAuthority(ORIGIN, client).authorize_field(
            TOKEN, Principal(TENANT, "17"), field_id
        )
    raw_path = requests[0].url.raw_path.decode()
    assert raw_path == "/api/v1/fields/id%3Ftenant%3Dother%23fragment", (
        "field input must remain one encoded path segment"
    )
    assert requests[0].url.query == b"", "field data cannot become query parameters"


@pytest.mark.parametrize(
    "field_id", ["id/../me", "id\\..\\me", ".", "..", "%2fme", "%252fme", "bad\udcff"]
)
@pytest.mark.asyncio
async def test_path_separators_and_ambiguous_encoded_field_ids_never_reach_platform(field_id):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SessionError) as failure:
            await PlatformAuthority(ORIGIN, client).authorize_field(
                TOKEN, Principal(TENANT, "17"), field_id
            )
    assert (failure.value.status, failure.value.code) == (422, "field_id_invalid"), (
        "reject field path traversal before a proxy can decode or normalize it"
    )
    assert not requests, "malformed field identifiers must not initiate an upstream read"


@pytest.mark.parametrize("bearer", [None, "", " ", "x\r\nX-Evil:yes", "x" * 16385])
@pytest.mark.asyncio
async def test_invalid_bearer_is_rejected_before_network(bearer):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=ME)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SessionError) as failure:
            await PlatformAuthority(ORIGIN, client).identity(bearer)
    assert failure.value.status == 401, (
        "missing or header-unsafe credentials must not reach the authority"
    )
    assert not calls, "reject malformed credentials before making any network request"


@pytest.mark.parametrize(
    "origin",
    [
        "http://external.example",
        "https://user:pass@example.com",
        "https://example.com/path",
        "https://example.com?query",
        "https://example.com#fragment",
        "ftp://example.com",
        "http://",
        "https://example.com:99999",
        "https://example.com\n",
        "//example.com",
    ],
)
def test_unsafe_configured_authority_origins_are_rejected(origin):
    client = httpx.AsyncClient()
    with pytest.raises(SessionError) as failure:
        PlatformAuthority(origin, client)
    assert (failure.value.status, failure.value.code) == (503, "platform_url_invalid"), (
        "bad origin configuration cannot redirect or disclose caller credentials"
    )


@pytest.mark.parametrize(
    "origin",
    [
        ORIGIN,
        "http://sahool-platform.railway.internal:8000/",
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
        "https://platform.example",
    ],
)
def test_supported_operator_configured_origins(origin):
    # Constructor validation performs no network activity and does not own the client.
    authority = PlatformAuthority(origin, httpx.AsyncClient())
    assert authority is not None, (
        "internal plaintext and external TLS origins are explicit supported configurations"
    )


@pytest.mark.asyncio
async def test_readiness_is_a_body_free_health_read():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text="health body is intentionally ignored")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await PlatformAuthority(ORIGIN, client).ready() is True, (
            "healthy platform dependency is ready"
        )
    assert requests[0].url.path == "/healthz", "readiness uses only the canonical health route"
    assert "Authorization" not in requests[0].headers, "readiness needs no participant credential"
