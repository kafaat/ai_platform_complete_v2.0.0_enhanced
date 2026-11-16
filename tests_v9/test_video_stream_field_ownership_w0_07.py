"""W0-07 (finding scout-1): a video stream may bind only a field of its own tenant.

Before: ``create_stream`` accepted any ``field_id``; the edge then synced the stream's
detections under the single tenant of ``EDGE_SYNC_TOKEN``, so a stream could write detections
into that tenant's fields. Now the field owner (field-management-service) is asked, with a
tenant assertion for the JWT's tenant, before the stream exists; and each frame tells the edge
the stream's tenant with a signed assertion.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi import HTTPException

from shared.security.service_tenant_assertion import verify_tenant_assertion

pytestmark = pytest.mark.unit

VIDEO = Path(__file__).resolve().parents[1] / "services" / "video-processor"
FIELD_KEY = "w0-07-field-service-assertion-key-012345"
EDGE_KEY = "w0-07-edge-assertion-key-0123456789abcdef"
TENANT_A = "tenant_a"


@pytest.fixture
def vp(monkeypatch):
    monkeypatch.syspath_prepend(str(VIDEO))
    for name in ("main", "router_registry", "routers", "routers.streams", "routers.health"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    cv2 = types.ModuleType("cv2")
    cv2.imencode = lambda ext, frame: (True, np.frombuffer(b"\xff\xd8jpeg", dtype=np.uint8))
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    from tests_v9.service_module import load_service_main

    module = load_service_main(str(VIDEO), required_attrs=("run_inference", "create_stream"))
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "agent-token")
    monkeypatch.setenv("FIELD_SERVICE_TENANT_ASSERTION_KEY", FIELD_KEY)
    try:
        yield module
    finally:
        for state in list(module.STREAMS.values()):
            state.status = "inactive"
            if state.task:
                state.task.cancel()
        module.STREAMS.clear()
        for name in ("main", "router_registry", "routers", "routers.streams", "routers.health"):
            sys.modules.pop(name, None)


def _owner(vp, monkeypatch, owned: set[str], status: int | None = None):
    """field-management stand-in at the HTTP boundary: 200 for owned fields, 404 otherwise."""
    seen: list[httpx.Request] = []
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status is not None:
            return httpx.Response(status)
        field = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200 if field in owned else 404, json={})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(vp.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    return seen


async def _create(vp, field_id):
    req = vp.CreateStreamRequest(stream_id="s1", usb_index=0, field_id=field_id)
    return await vp.create_stream(req, user={"tenant_id": TENANT_A, "role": "user"})


async def test_a_stream_naming_another_tenants_field_is_403_and_not_created(vp, monkeypatch):
    seen = _owner(vp, monkeypatch, owned={"field-own"})
    with pytest.raises(HTTPException) as exc:
        await _create(vp, "field-foreign")
    assert exc.value.status_code == 403, exc.value.detail
    assert "s1" not in vp.STREAMS, "a stream bound to a foreign field was created"
    request = seen[0]
    claims = verify_tenant_assertion(
        request.headers["X-Tenant-Assertion"],
        {"current": FIELD_KEY},
        "video-processor",
        TENANT_A,
        expected_method="GET",
        expected_path="/internal/fields/field-foreign",
        expected_request_id=request.headers["X-Request-Id"],
    )
    assert claims.tenant_id == TENANT_A, "the owner is asked for the JWT's tenant"


async def test_a_stream_on_an_owned_field_is_created(vp, monkeypatch):
    _owner(vp, monkeypatch, owned={"field-own"})
    result = await _create(vp, "field-own")
    assert result["stream_id"] == "s1", result
    assert vp.STREAMS["s1"].config.field_id == "field-own", vp.STREAMS["s1"].config


@pytest.mark.parametrize("status", [401, 500, 503])
async def test_ownership_that_cannot_be_proved_fails_closed(vp, monkeypatch, status):
    _owner(vp, monkeypatch, owned={"field-own"}, status=status)
    with pytest.raises(HTTPException) as exc:
        await _create(vp, "field-own")
    assert exc.value.status_code == 503, exc.value.detail
    assert "s1" not in vp.STREAMS, "created without a proved owner"


async def test_missing_field_service_key_fails_closed(vp, monkeypatch):
    seen = _owner(vp, monkeypatch, owned={"field-own"})
    monkeypatch.delenv("FIELD_SERVICE_TENANT_ASSERTION_KEY")
    with pytest.raises(HTTPException) as exc:
        await _create(vp, "field-own")
    assert exc.value.status_code == 503, exc.value.detail
    assert seen == [], "no unsigned ownership query is sent"


async def test_an_unbound_stream_needs_no_owner(vp, monkeypatch):
    seen = _owner(vp, monkeypatch, owned=set())
    result = await _create(vp, "unknown")
    assert result["stream_id"] == "s1", result
    assert seen == [], "an unbound stream has no field to check"


async def test_each_frame_tells_the_edge_the_streams_tenant_signed(vp, monkeypatch):
    monkeypatch.setenv("EDGE_TENANT_ASSERTION_KEY", EDGE_KEY)
    calls = []
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"detections": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(vp.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    cfg = vp.StreamConfig(stream_id="s1", field_id="field-own", tenant_id=TENANT_A)
    await vp.run_inference(np.zeros((4, 4, 3), dtype=np.uint8), cfg)
    request = calls[0]
    claims = verify_tenant_assertion(
        request.headers["X-Tenant-Assertion"],
        {"current": EDGE_KEY},
        "video-processor",
        TENANT_A,
        expected_method="POST",
        expected_path="/v1/inference/pest-detect",
        expected_request_id=request.headers["X-Request-Id"],
    )
    assert claims.tenant_id == TENANT_A, claims
