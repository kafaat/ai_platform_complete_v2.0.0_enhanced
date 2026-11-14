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
        ("rag-retrieval", 503),
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
        upstream = (
            "knowledge-graph" if request.url.path == "/v1/edges" else "rag-retrieval"
        )
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
    assert ("upstream_status=%s" % http_status) in caplog.text
    assert visited == (
        ["knowledge-graph"]
        if dependency == "knowledge-graph"
        else ["knowledge-graph", "rag-retrieval"]
    )
