"""W0-02 (knowledge-1 / x-4): an empty or unavailable RAG corpus must not fail the advice.

Default compose seeds RAG into ``__seed_quarantine__``, so a real tenant has no readable
corpus and rag-retrieval answers 424 ``TENANT_CORPUS_EMPTY`` (older builds: a free-text
503); ``test_real_rag_retrieval_quarantine_only_corpus_end_to_end`` joins the real
rag-retrieval app for that state to the ai_agronomist degrade. Before
this fix ai_agronomist turned every RAG status >= 400 into a 502, so every
``/v1/chat|query|explain|recommend`` failed. Now 424/503 degrade exactly like the KG path:
the answer continues on canonical field-state evidence and declares
``rag_available: false`` with an allow-listed reason code. Other statuses still fail 502.

Only in-memory HTTP/ASGI transports and an in-memory Qdrant stand-in are used; no network,
Qdrant or database.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.ai_agronomist import ai_evidence_runtime as runtime
from tests_v9.test_b6m4_structured_advisory import FIELD, TENANT, state

pytestmark = pytest.mark.unit

_SECRET = "TOP_SECRET_RAG_UPSTREAM_BODY_and_TOKEN"


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _wire(monkeypatch, rag_response, seen=None):
    real_client = _REAL_ASYNC_CLIENT

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
    assert seen == ["/v1/search"], f"Without a trusted crop, KG must not be queried: {seen}"
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


def test_trusted_field_crop_queries_scoped_kg_before_rag(monkeypatch):
    """A canonical crop reference enables scoped KG expansion; an untrusted crop cannot."""
    seen: list[str] = []
    _wire(monkeypatch, _corpus_empty, seen)
    owner_state = state()
    owner_state["ai_context_pack"] = {
        "crop_knowledge": {"status": "reference_only", "crop_id": "wheat"}
    }
    monkeypatch.setattr(
        runtime, "_fetch_canonical_field_state", AsyncMock(return_value=owner_state)
    )
    response = _chat(monkeypatch)
    assert response.status_code == 200, response.text
    assert seen == ["/v1/edges", "/v1/search"], seen
    assert response.json()["rag_available"] is False


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,expected_transport_reason",
    [
        (httpx.ConnectError, "advisory_dependency_unavailable"),
        (httpx.ReadTimeout, "advisory_dependency_timeout"),
    ],
)
async def test_rag_transport_failure_degrades_without_inventing_an_upstream_response(
    monkeypatch, caplog, failure, expected_transport_reason
):
    """A missing RAG host is not an HTTP 503 and must not fail field-state advice."""

    from services.ai_agronomist.main import AdvisorQuery

    def unavailable():
        raise failure(_SECRET)

    _wire(monkeypatch, unavailable)
    result = await runtime.build_evidence_response(
        AdvisorQuery(question="ما حالة الحقل؟", field_id=FIELD),
        endpoint_mode="chat",
        x_tenant_id=TENANT,
        save_agent_tool_audit=lambda _: None,
        save_pending_approval=lambda _: None,
    )
    assert result["status"] == "ok"
    assert result["rag_available"] is False
    assert result["rag_unavailable_reason"] == "rag_transport_unavailable"
    evidence = result["annotations"]["rag_retrieval"]
    assert evidence["available"] is False
    assert evidence["upstream_status"] is None
    assert evidence["transport_reason"] == expected_transport_reason
    assert len(evidence["correlation_id"]) == 32
    assert _SECRET not in repr(result)
    assert _SECRET not in caplog.text
    assert result["annotations"]["rag"] == []


@pytest.fixture
def _restore_sys_modules():
    """rag-retrieval's ``main`` (and its generic sibling modules) must not outlive this test.

    ``load_service_main`` restores ``sys.path`` but leaves the loaded modules in
    ``sys.modules``; a later test that patches ``"main._pool"`` by name (auth) would then
    patch rag-retrieval's module. Snapshot and restore the module table around the test.
    """
    saved = dict(sys.modules)
    yield
    for name in list(sys.modules):
        if name not in saved:
            del sys.modules[name]
    sys.modules.update(saved)


def test_real_rag_retrieval_quarantine_only_corpus_end_to_end(monkeypatch, _restore_sys_modules):
    """Default compose, joined end to end: real rag-retrieval with only quarantined seeds.

    The RAG call goes through the real rag-retrieval FastAPI app (auth, tenant guard,
    readiness, error serialization) over an ASGI transport; Qdrant is an in-memory store
    holding only ``__seed_quarantine__`` points, as the default compose seeding leaves it.
    """
    from tests_v9.service_module import load_service_main
    from tests_v9.test_rag_owned_gap_witnesses import ROOT, chunk, wire

    rag = load_service_main(
        str(ROOT / "services/rag-retrieval"), required_attrs=("_ensure_sparse_index", "search")
    )
    wire(rag, [chunk("__seed_quarantine__")])
    token = "w0-02-test-agent-token"
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", token)
    monkeypatch.setattr(runtime, "AGENT_TOKEN", token)
    rag_transport = httpx.ASGITransport(app=rag.app)
    seen: list[tuple[str, int]] = []

    async def transport(request):
        if request.url.path == "/v1/search":
            async with _REAL_ASYNC_CLIENT(
                transport=rag_transport, base_url="http://rag-retrieval"
            ) as rag_client:
                resp = await rag_client.post(
                    "/v1/search", content=request.content, headers=dict(request.headers)
                )
            seen.append((request.url.path, resp.status_code))
            return httpx.Response(resp.status_code, content=resp.content, headers=resp.headers)
        seen.append((request.url.path, 200))
        return httpx.Response(200, json={"edges": []})

    _wire(monkeypatch, lambda: None)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(transport), **kw),
    )
    resp = _chat(monkeypatch)
    assert resp.status_code == 200, resp.text
    assert ("/v1/search", 424) in seen, f"real rag-retrieval must answer 424: {seen}"
    body = resp.json()
    assert body["rag_available"] is False, body.get("rag_available")
    assert body["rag_unavailable_reason"] == "TENANT_CORPUS_EMPTY", body["rag_unavailable_reason"]
    assert body["annotations"]["rag_retrieval"]["upstream_status"] == 424, body["annotations"]
