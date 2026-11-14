"""Exercise proxy byte/header/query fidelity through the complete platform ASGI app.

Only identity and upstream transport are replaced; routing and RBAC remain real.
"""

import asyncio
import gzip

import httpx
import pytest
from api import main as platform
from api.routers import service_proxy
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

TENANT = "11111111-1111-4111-8111-111111111111"
REAL_ASYNC_CLIENT = httpx.AsyncClient


def roundtrip(
    monkeypatch,
    *,
    payload=b'{"accepted":true}',
    upstream_headers=None,
    status=200,
    method="GET",
    path="/api/soil/v1/fields/f1/soil/profile",
    role=UserRole.OWNER,
    authenticate=True,
    client_headers=None,
    body=None,
):
    seen = []

    def upstream(request):
        seen.append(request)
        return httpx.Response(
            status,
            content=payload,
            headers=upstream_headers or {"content-type": "application/json"},
        )

    transport = httpx.MockTransport(upstream)
    monkeypatch.setattr(
        service_proxy.httpx,
        "AsyncClient",
        lambda **kw: REAL_ASYNC_CLIENT(transport=transport, **kw),
    )
    monkeypatch.setattr(platform, "_RATE_LIMIT_PER_MIN", 0)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "review-only-service-token")
    monkeypatch.setenv("SOIL_SERVICE_URL", "http://soil-upstream.local")
    if authenticate:
        user = UserSchema(
            user_id="verified-actor", tenant_id=TENANT, role=role, name_ar="review", is_active=True
        )

        async def identity():
            return user

        monkeypatch.setitem(platform.app.dependency_overrides, platform.get_current_user, identity)
    else:
        monkeypatch.delitem(
            platform.app.dependency_overrides, platform.get_current_user, raising=False
        )

    async def run():
        request = httpx.Request(
            method, "http://platform.local" + path, headers=client_headers, content=body
        )
        response = await httpx.ASGITransport(app=platform.app).handle_async_request(request)
        # ASGITransport's direct response leaves bytes undecoded. This permits an
        # assertion on the actual HTTP representation without hiding decoder errors.
        wire = b"".join([part async for part in response.stream])
        return response, wire

    response, wire = asyncio.run(run())
    return response, wire, seen


def test_gzip_response_obeys_its_content_encoding(monkeypatch):
    plain = b'{"accepted":true}'
    response, wire, seen = roundtrip(
        monkeypatch,
        payload=gzip.compress(plain),
        upstream_headers={"content-type": "application/json", "content-encoding": "gzip"},
    )
    assert response.status_code == 200 and len(seen) == 1
    decoded = gzip.decompress(wire) if response.headers.get("content-encoding") == "gzip" else wire
    assert decoded == plain


def test_identity_response_and_content_length_are_correct(monkeypatch):
    response, wire, seen = roundtrip(monkeypatch)
    assert response.status_code == 200 and wire == b'{"accepted":true}'
    assert int(response.headers["content-length"]) == len(wire)
    assert "content-encoding" not in response.headers
    assert len(seen) == 1


def test_soil_proxy_replaces_actor_tenant_service_credentials(monkeypatch):
    _, _, seen = roundtrip(
        monkeypatch,
        client_headers={
            "Authorization": "Bearer client-secret",
            "Cookie": "sid=client-secret",
            "X-Tenant-Id": "spoofed",
            "X-Actor-Id": "spoofed",
            "X-Agent-Token": "spoofed",
            "X-Field-Forms-Token": "spoofed",
        },
    )
    h = seen[0].headers
    assert h["x-tenant-id"] == TENANT and h["x-actor-id"] == "verified-actor"
    assert h["x-agent-token"] == "review-only-service-token"
    assert "authorization" not in h and "cookie" not in h and "x-field-forms-token" not in h


def test_duplicate_query_values_and_encoding_are_preserved(monkeypatch):
    _, _, seen = roundtrip(
        monkeypatch, path="/api/soil/v1/fields/f1/soil/profile?tag=one&tag=two&q=a%2Bb+space"
    )
    assert seen[0].url.params.get_list("tag") == ["one", "two"]
    assert seen[0].url.params["q"] == "a+b space"


def test_upstream_redirect_is_not_followed_with_service_token(monkeypatch):
    response, _, seen = roundtrip(
        monkeypatch,
        status=307,
        payload=b"",
        upstream_headers={"location": "http://different-origin.local/collect"},
    )
    assert response.status_code == 307 and len(seen) == 1
    assert str(seen[0].url).startswith("http://soil-upstream.local/")


def test_anonymous_request_never_reaches_upstream(monkeypatch):
    response, _, seen = roundtrip(monkeypatch, authenticate=False)
    assert response.status_code == 401 and not seen


def test_viewer_write_denied_before_upstream(monkeypatch):
    response, _, seen = roundtrip(
        monkeypatch,
        method="POST",
        path="/api/soil/v1/soil/ingest",
        role=UserRole.VIEWER,
        body=b"{}",
    )
    assert response.status_code == 403 and not seen


def test_allowed_post_body_is_preserved(monkeypatch):
    body = b'{"value": 12.50, "note":"review"}'
    response, _, seen = roundtrip(
        monkeypatch,
        method="POST",
        path="/api/soil/v1/soil/ingest",
        body=body,
        client_headers={"content-type": "application/json"},
    )
    assert response.status_code == 200 and seen[0].content == body


def test_unlisted_path_denied_before_upstream(monkeypatch):
    response, _, seen = roundtrip(monkeypatch, path="/api/soil/internal/admin")
    assert response.status_code == 404 and not seen


def test_single_query_value_retains_plus_and_space(monkeypatch):
    _, _, seen = roundtrip(monkeypatch, path="/api/soil/v1/fields/f1/soil/profile?q=a%2Bb+space")
    assert seen[0].url.params["q"] == "a+b space"


def _httpx_decodes(coding):
    with httpx.Client() as probe:
        return coding in probe.headers.get("accept-encoding", "")


@pytest.mark.parametrize("coding", ["br", "zstd", "compress"])
def test_a_coding_httpx_cannot_decode_keeps_its_label(monkeypatch, coding):
    """ROUTE-01 review: stripping Content-Encoding unconditionally sent raw br/zstd bytes
    labelled identity. Only codings httpx actually decoded may lose their label."""
    if _httpx_decodes(coding):
        pytest.skip(f"httpx decodes {coding} in this environment; covered by the gzip case")
    raw = b"\x8b\x07\x80opaque-encoded-bytes\x03"
    response, wire, _ = roundtrip(
        monkeypatch,
        payload=raw,
        upstream_headers={"content-type": "application/json", "content-encoding": coding},
    )
    assert response.status_code == 200
    assert wire == raw and response.headers.get("content-encoding") == coding


def test_client_accept_encoding_is_not_forwarded_upstream(monkeypatch):
    """httpx advertises only what it can decode; the browser's br/zstd must not reach upstream."""
    _, _, seen = roundtrip(monkeypatch, client_headers={"Accept-Encoding": "br, zstd"})
    advertised = {c.strip() for c in seen[0].headers.get("accept-encoding", "").split(",")}
    assert "zstd" not in advertised or _httpx_decodes("zstd")
    assert "br" not in advertised or _httpx_decodes("br")
    assert advertised <= {"gzip", "deflate", "br", "zstd"}
