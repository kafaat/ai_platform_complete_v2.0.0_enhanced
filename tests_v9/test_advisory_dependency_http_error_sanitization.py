"""RAG/KG HTTP failures must not expose internal upstream bodies to the farmer client.

The live evidence builder is driven only until the first failed dependency using
an in-memory transport. No tenant data, Qdrant collection, or network are touched.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependency,http_status",
    [
        ("knowledge-graph", 500),
        ("knowledge-graph", 503),
        ("rag-retrieval", 400),
        ("rag-retrieval", 401),
        ("rag-retrieval", 403),
        ("rag-retrieval", 500),
        ("rag-retrieval", 502),
        # 424/503 from rag-retrieval degrade to rag_available:false (W0-02); their
        # non-reflection is pinned in test_ai_rag_tenant_corpus_empty_degrade.py.
    ],
)
async def test_upstream_response_body_is_never_reflected(
    monkeypatch, caplog, dependency, http_status
):
    from services.ai_agronomist import ai_evidence_runtime as runtime

    real_client = httpx.AsyncClient
    tenant_id = "ad063907-fc11-4314-b639-e1c91d820960"
    secret = "TOP_SECRET_INTERNAL_STACK_TRACE_and_TOKEN"
    visited = []

    async def transport(request):
        upstream = "knowledge-graph" if request.url.path == "/v1/edges" else "rag-retrieval"
        visited.append(upstream)
        assert request.headers["X-Tenant-Id"] == tenant_id
        if upstream == dependency:
            return httpx.Response(http_status, text=secret)
        return httpx.Response(200, json={"edges": []})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    request = SimpleNamespace(
        tenant_id=tenant_id,
        current_field_state=None,
        field_id=None,
        crop="wheat",
        question="ما حالة القمح؟",
        region=None,
        final_k=5,
        voice_read_only=False,
    )
    with pytest.raises(HTTPException) as exc:
        await runtime.build_evidence_response(
            request,
            endpoint_mode="evidence",
            x_tenant_id=tenant_id,
            save_agent_tool_audit=lambda record: None,
            save_pending_approval=lambda record: None,
        )

    error = exc.value
    assert error.status_code == 502
    assert error.detail["dependency"] == dependency
    assert error.detail["reason_code"] == "advisory_dependency_unavailable"
    correlation = error.detail["correlation_id"]
    assert len(correlation) == 32
    assert secret not in str(error.detail)
    assert secret not in caplog.text
    assert f"upstream_status={http_status}" in caplog.text
    assert visited == (
        ["knowledge-graph"]
        if dependency == "knowledge-graph"
        else ["knowledge-graph", "rag-retrieval"]
    )


_SECRET = "TOP_SECRET_PLATFORM_BODY_and_TOKEN"
_CRED_URL = "http://svc:PASSWORD_SHOULD_NOT_LEAK@platform:8000"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["http_500", "connect_error"])
async def test_platform_field_state_failure_keeps_body_and_url_out_of_the_log(
    monkeypatch, caplog, mode
):
    """Lab receipt for #1471: the platform field-state path logged resp.text and repr(exc)."""
    import logging

    from services.ai_agronomist import ai_evidence_runtime as runtime

    real_client = httpx.AsyncClient

    async def transport(request):
        if mode == "connect_error":
            raise httpx.ConnectError(f"connect to {_CRED_URL} failed: {_SECRET}", request=request)
        return httpx.Response(500, text=_SECRET)

    monkeypatch.setattr(runtime, "PLATFORM_URL", _CRED_URL)
    monkeypatch.setattr(runtime, "AGENT_TOKEN", "agent-token")
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    caplog.set_level(logging.DEBUG)
    async with httpx.AsyncClient() as client:
        out = await runtime._fetch_canonical_field_state(
            client, tenant_id="ad063907-fc11-4314-b639-e1c91d820960", field_id="field-1"
        )
    assert out["status"] == "unavailable"
    assert set(out) == {"status", "reason", "correlation_id"}
    # This module's own log lines. httpx's INFO request line is a separate, process-wide logger
    # (the repo redacts it per service, e.g. the TTS bot URL); it is not changed here.
    logged = "\n".join(
        r.getMessage() for r in caplog.records if r.name == "ai_agronomist.evidence_runtime"
    )
    assert _SECRET not in logged
    assert "PASSWORD_SHOULD_NOT_LEAK" not in logged
    assert out["correlation_id"] in logged


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["http_500", "connect_error"])
async def test_ai_advice_audit_event_returned_to_the_client_has_no_upstream_text(monkeypatch, mode):
    """Review of #1471: audit_event (returned to the client) carried resp.text / str(exc)."""
    from services.ai_agronomist import ai_evidence_runtime as runtime

    real_client = httpx.AsyncClient

    async def transport(request):
        if mode == "connect_error":
            raise httpx.ConnectError(f"connect to {_CRED_URL}: {_SECRET}", request=request)
        return httpx.Response(500, text=_SECRET)

    monkeypatch.setattr(runtime, "PLATFORM_URL", _CRED_URL)
    monkeypatch.setattr(runtime, "AGENT_TOKEN", "agent-token")
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    event = await runtime._record_ai_advice_event(
        tenant_id="ad063907-fc11-4314-b639-e1c91d820960",
        field_id=None,
        question="q",
        evidence_ids=[],
        confidence=0.5,
        selected_imagery_date=None,
        endpoint_mode="test",
    )
    assert event["status"] == "failed"
    text = repr(event)
    assert _SECRET not in text
    assert "PASSWORD_SHOULD_NOT_LEAK" not in text
