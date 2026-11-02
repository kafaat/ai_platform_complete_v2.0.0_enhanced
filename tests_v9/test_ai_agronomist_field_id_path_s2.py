"""S2 (audit 2026-11-01): ``field_id`` was interpolated raw into
``/internal/fields/{field_id}/state`` sent with the service token, so ``../../x#`` reached
other internal paths; the platform's error body (and exception text) was echoed back to
the caller through the 502. The platform is mocked; nothing leaves the box.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from services.ai_agronomist import ai_evidence_runtime as runtime  # noqa: E402
from services.ai_agronomist import main as M  # noqa: E402

_TRAVERSAL_IDS = ["../../internal/events/ai-advice#", "f1/../../x", "f1?tenant_id=t2", "f 1", "f1#"]


@pytest.mark.parametrize("bad", _TRAVERSAL_IDS)
async def test_s2_non_canonical_field_id_never_reaches_the_platform(monkeypatch, bad):
    monkeypatch.setattr(runtime, "AGENT_TOKEN", "unit-credential")
    client = SimpleNamespace(get=AsyncMock(return_value=httpx.Response(200, json={})))
    result = await runtime._fetch_canonical_field_state(client, tenant_id="t1", field_id=bad)
    client.get.assert_not_awaited()
    assert result["status"] == "unavailable"


async def test_s2_path_segment_is_percent_encoded(monkeypatch):
    """Defence in depth: even if validation were bypassed, ``/`` cannot leave the segment."""
    monkeypatch.setattr(runtime, "AGENT_TOKEN", "unit-credential")
    monkeypatch.setattr(runtime, "is_canonical_field_id", lambda _v: True, raising=False)
    client = SimpleNamespace(get=AsyncMock(return_value=httpx.Response(404)))
    await runtime._fetch_canonical_field_state(client, tenant_id="t1", field_id="../x#y")
    url = client.get.call_args.args[0]
    assert url.endswith("/internal/fields/..%2Fx%23y/state"), url


async def test_s2_upstream_error_body_is_not_echoed(monkeypatch):
    monkeypatch.setattr(runtime, "AGENT_TOKEN", "unit-credential")
    leaked = "internal-stacktrace postgres://svc:pw@db/sahool"
    client = SimpleNamespace(get=AsyncMock(return_value=httpx.Response(500, text=leaked)))
    result = await runtime._fetch_canonical_field_state(client, tenant_id="t1", field_id="fld_1")
    assert result["status"] == "unavailable"
    assert result.get("correlation_id")
    assert "postgres" not in json.dumps(result) and "stacktrace" not in json.dumps(result)


async def test_s2_transport_exception_text_is_not_echoed(monkeypatch):
    monkeypatch.setattr(runtime, "AGENT_TOKEN", "unit-credential")
    client = SimpleNamespace(
        get=AsyncMock(side_effect=RuntimeError("connect http://sahool-platform:8000 failed"))
    )
    result = await runtime._fetch_canonical_field_state(client, tenant_id="t1", field_id="fld_1")
    assert result["status"] == "unavailable" and result.get("correlation_id")
    assert "sahool-platform" not in json.dumps(result)


@pytest.mark.parametrize("bad", _TRAVERSAL_IDS)
def test_s2_advisor_query_rejects_non_canonical_field_id(bad):
    with pytest.raises(ValidationError):
        M.AdvisorQuery(question="q", field_id=bad)


@pytest.mark.parametrize("good", ["fld_0a1b2c3d4e5f", "11111111-1111-4111-8111-111111111111", ""])
def test_s2_advisor_query_accepts_canonical_field_ids(good):
    assert M.AdvisorQuery(question="q", field_id=good).field_id == good


async def test_s2_runtime_rejects_bad_field_id_before_any_dependency(monkeypatch):
    """The runtime refuses on its own too (a caller that skips the model still gets 422)."""
    fetch = AsyncMock(side_effect=AssertionError("fetched with a non-canonical field_id"))
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", fetch)
    # model_construct skips validation: this is the runtime's own check, not the model's.
    req = M.AdvisorQuery.model_construct(question="q", field_id="../../internal/events/ai-advice#")
    with pytest.raises(HTTPException) as exc:
        await runtime.build_evidence_response(
            req,
            endpoint_mode="chat",
            x_tenant_id="t1",
            save_agent_tool_audit=lambda _: None,
            save_pending_approval=lambda _: None,
        )
    assert exc.value.status_code == 422
    fetch.assert_not_awaited()
