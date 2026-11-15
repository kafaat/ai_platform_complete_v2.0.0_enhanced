"""W0-02 (knowledge-1 / x-4): an empty or unavailable RAG corpus must not fail the advice.

Default compose seeds RAG into ``__seed_quarantine__``, so a real tenant has no readable
corpus and rag-retrieval answers 424 ``TENANT_CORPUS_EMPTY`` (older builds: 503). Before
this fix ai_agronomist turned every RAG status >= 400 into a 502, so every
``/v1/chat|query|explain|recommend`` failed. Now 424/503 degrade exactly like the KG path:
the answer continues on canonical field-state evidence and declares
``rag_available: false`` with an allow-listed reason code. Other statuses still fail 502.

Only in-memory HTTP transports are used; no network, Qdrant or database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.ai_agronomist import ai_evidence_runtime as runtime
from tests_v9.test_b6m4_structured_advisory import FIELD, TENANT, state

pytestmark = pytest.mark.unit

_SECRET = "TOP_SECRET_RAG_UPSTREAM_BODY_and_TOKEN"


def _wire(monkeypatch, rag_response, seen=None):
    real_client = httpx.AsyncClient

    def transport(request):
        if seen is not None:
            seen.append(request.url.path)
        if request.url.path == "/v1/search":
            return rag_response()
        return httpx.Response(200, json={"edges": []})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(transport), **kw),
    )
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", AsyncMock(return_value=state()))
    monkeypatch.setattr(runtime, "_generation_allowed", lambda _: False)
    monkeypatch.setattr(
        runtime, "_record_ai_advice_event", AsyncMock(return_value={"persisted": True})
    )


def _corpus_empty():
    return httpx.Response(
        424,
        json={
            "detail": {
                "code": "TENANT_CORPUS_EMPTY",
                "message": "tenant has no active readable corpus",
            }
        },
    )


def _chat(monkeypatch):
    from services.ai_agronomist import main

    client = TestClient(main.app)
    return client.post(
        "/v1/chat",
        json={"question": "ما حالة الحقل؟", "field_id": FIELD, "crop": "wheat"},
        headers={"X-Tenant-Id": TENANT},
    )


def test_chat_with_empty_tenant_corpus_returns_200_on_field_state_evidence(monkeypatch):
    seen: list[str] = []
    _wire(monkeypatch, _corpus_empty, seen)
    resp = _chat(monkeypatch)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert seen == ["/v1/edges", "/v1/search"], f"KG then RAG must both be asked: {seen}"
    assert body["rag_available"] is False, body.get("rag_available")
    assert body["rag_unavailable_reason"] == "TENANT_CORPUS_EMPTY", body["rag_unavailable_reason"]
    rag_meta = body["annotations"]["rag_retrieval"]
    assert rag_meta["available"] is False, rag_meta
    assert rag_meta["upstream_status"] == 424, rag_meta
    assert len(rag_meta["correlation_id"]) == 32, rag_meta
    assert body["annotations"]["rag"] == [], body["annotations"]["rag"]
    sources = {s["key"]: s for s in body["evidence_sources"]}
    assert sources["field_state"]["available"] is True, sources
    assert sources["rag"]["available"] is False, sources
    assert "حالة الحقل" in body["answer_ar"], body["answer_ar"]
    assert body["annotations"]["canonical_field_state"]["field_id"] == FIELD, (
        "the answer must carry the canonical field-state evidence"
    )


def test_healthy_rag_declares_available(monkeypatch):
    _wire(monkeypatch, lambda: httpx.Response(200, json={"annotations": []}))
    body = _chat(monkeypatch).json()
    assert body["rag_available"] is True, body.get("rag_available")
    assert body["rag_unavailable_reason"] is None, body["rag_unavailable_reason"]
    assert body["annotations"]["rag_retrieval"] == {"available": True}, body["annotations"]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint_mode", ["chat", "query", "explain", "recommend_evidence_only"])
@pytest.mark.parametrize(
    "rag_response,reason",
    [
        (_corpus_empty, "TENANT_CORPUS_EMPTY"),
        (
            lambda: httpx.Response(503, json={"detail": "rag_retrieval_unavailable"}),
            "rag_retrieval_unavailable",
        ),
        # Older rag-retrieval answered an empty corpus with a free-text 503.
        (
            lambda: httpx.Response(
                503,
                json={
                    "detail": "hybrid sparse index not ready: tenant has no active readable corpus"
                },
            ),
            "rag_upstream_http_503",
        ),
        (lambda: httpx.Response(503, text=_SECRET), "rag_upstream_http_503"),
        (
            lambda: httpx.Response(424, json={"detail": {"code": _SECRET}}),
            "rag_upstream_http_424",
        ),
    ],
)
async def test_degradable_rag_statuses_never_fail_and_never_reflect_bodies(
    monkeypatch, caplog, endpoint_mode, rag_response, reason
):
    from services.ai_agronomist.main import AdvisorQuery

    _wire(monkeypatch, rag_response)
    result = await runtime.build_evidence_response(
        AdvisorQuery(question="ما حالة الحقل؟", field_id=FIELD),
        endpoint_mode=endpoint_mode,
        x_tenant_id=TENANT,
        save_agent_tool_audit=lambda _: None,
        save_pending_approval=lambda _: None,
    )
    assert result["status"] == "ok", result["status"]
    assert result["rag_available"] is False, result["rag_available"]
    assert result["rag_unavailable_reason"] == reason, result["rag_unavailable_reason"]
    assert _SECRET not in repr(result), "upstream body must never be reflected to the client"
    assert _SECRET not in caplog.text, "upstream body must never be logged"
    assert result["annotations"]["rag_retrieval"]["correlation_id"] in caplog.text, (
        "the degradation must be logged with its correlation id"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("http_status", [400, 401, 403, 404, 422, 500, 502])
async def test_non_degradable_rag_statuses_still_fail_closed(monkeypatch, http_status):
    from services.ai_agronomist.main import AdvisorQuery

    _wire(monkeypatch, lambda: httpx.Response(http_status, text=_SECRET))
    with pytest.raises(HTTPException) as exc:
        await runtime.build_evidence_response(
            AdvisorQuery(question="ما حالة الحقل؟", field_id=FIELD),
            endpoint_mode="chat",
            x_tenant_id=TENANT,
            save_agent_tool_audit=lambda _: None,
            save_pending_approval=lambda _: None,
        )
    assert exc.value.status_code == 502, exc.value.status_code
    assert exc.value.detail["dependency"] == "rag-retrieval", exc.value.detail
    assert _SECRET not in str(exc.value.detail), "upstream body must never be reflected"
