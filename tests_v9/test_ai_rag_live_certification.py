from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "scripts/ci/ai_rag_live_certification.py"


def mod():
    spec = importlib.util.spec_from_file_location("ai_rag_live_cert", P)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ok_qdrant():
    return {
        "result": {
            "config": {"params": {"vectors": {"size": 3}}},
            "points_count": 10,
        }
    }


def test_live_certification_passes_read_only_local_chain(monkeypatch):
    m = mod()

    def req(method, url, payload=None, headers=None, timeout_s=20.0):
        if url.endswith("/api/version"):
            return m.HTTPResult(200, {"version": "0.32.5"}, "")
        if url.endswith("/v1/models"):
            return m.HTTPResult(
                200, {"data": [{"id": "llama3.2:3b"}, {"id": "nomic-embed-text"}]}, ""
            )
        if url.endswith("/api/embeddings"):
            return m.HTTPResult(200, {"embedding": [0.1, 0.2, 0.3]}, "")
        if url.endswith("/v1/chat/completions"):
            return m.HTTPResult(200, {"choices": [{"message": {"content": "SAHOOL_OK"}}]}, "")
        if "/collections/" in url:
            key = (headers or {}).get("api-key")
            if key == "secret":
                return m.HTTPResult(200, _ok_qdrant(), "")
            return m.HTTPResult(401, {"status": "unauthorized"}, "")
        if url.endswith("/readyz") and "rag" in url:
            return m.HTTPResult(
                200,
                {
                    "status": "ready",
                    "embedding_contract_parity": True,
                    "collection_vector_schema_parity": True,
                    "sparse_index_hydrated": True,
                    "sparse_index_count": 10,
                    "vector_size": 3,
                },
                "",
            )
        if url.endswith("/v1/search"):
            if payload["tenant_id"].endswith("-other") or payload["tenant_id"] == "__global__":
                return m.HTTPResult(403, {"detail": "blocked"}, "")
            return m.HTTPResult(
                200,
                {
                    "annotations": [
                        {
                            "chunk_id": "seed:1",
                            "retrieval": {
                                "dense_score": 0.8,
                                "bm25_score": 0.5,
                                "fused_score": 0.7,
                            },
                        }
                    ]
                },
                "",
            )
        if url.endswith("/healthz/ai-provider"):
            return m.HTTPResult(
                200,
                {
                    "generation_enabled": False,
                    "provider": "local",
                    "provider_class": "local",
                    "available": True,
                    "model": "llama3.2:3b",
                    "wire_format": "openai_chat",
                },
                "",
            )
        raise AssertionError((method, url, payload, headers))

    monkeypatch.setattr(m, "_request", req)
    result = m.certify(
        tenant_id="tenant-a",
        field_id=None,
        crop=None,
        ollama_url="http://ollama",
        qdrant_url="http://qdrant",
        rag_url="http://rag",
        ai_url="http://ai",
        collection="sahool_agri_kb",
        qdrant_api_key="secret",
        expected_ollama_version="0.32.5",
        chat_model="llama3.2:3b",
        embed_model="nomic-embed-text",
        hybrid_query="القمح GDD",
        require_generation=False,
        timeout_s=1,
    )
    assert result["status"] == "PASS"
    assert result["read_only"] is True
    assert result["audit_write_requested"] is False
    assert result["audit_write_scope"] is None
    assert result["authority_promotion"] is False
    assert all(c["status"] == "PASS" for c in result["checks"])


def test_generation_requirement_is_evidence_required_not_fake_pass(monkeypatch):
    m = mod()

    def req(method, url, payload=None, headers=None, timeout_s=20.0):
        if url.endswith("/api/version"):
            return m.HTTPResult(200, {"version": "0.32.5"}, "")
        if url.endswith("/v1/models"):
            return m.HTTPResult(
                200, {"data": [{"id": "llama3.2:3b"}, {"id": "nomic-embed-text"}]}, ""
            )
        if url.endswith("/api/embeddings"):
            return m.HTTPResult(200, {"embedding": [1, 2, 3]}, "")
        if url.endswith("/v1/chat/completions"):
            return m.HTTPResult(200, {"choices": [{"message": {"content": "ok"}}]}, "")
        if "/collections/" in url:
            return (
                m.HTTPResult(200, _ok_qdrant(), "")
                if (headers or {}).get("api-key") == "secret"
                else m.HTTPResult(403, {}, "")
            )
        if url.endswith("/readyz"):
            return m.HTTPResult(
                200,
                {
                    "status": "ready",
                    "embedding_contract_parity": True,
                    "collection_vector_schema_parity": True,
                    "sparse_index_hydrated": True,
                    "sparse_index_count": 2,
                    "vector_size": 3,
                },
                "",
            )
        if url.endswith("/v1/search"):
            if payload["tenant_id"] != "t":
                return m.HTTPResult(403, {}, "")
            return m.HTTPResult(
                200,
                {
                    "annotations": [
                        {
                            "chunk_id": "x",
                            "retrieval": {
                                "dense_score": 1.0,
                                "bm25_score": 1.0,
                                "fused_score": 1.0,
                            },
                        }
                    ]
                },
                "",
            )
        if url.endswith("/healthz/ai-provider"):
            return m.HTTPResult(
                200,
                {
                    "generation_enabled": False,
                    "provider": "local",
                    "provider_class": "local",
                    "available": True,
                    "model": "llama3.2:3b",
                    "wire_format": "openai_chat",
                },
                "",
            )
        raise AssertionError(url)

    monkeypatch.setattr(m, "_request", req)
    result = m.certify(
        tenant_id="t",
        field_id=None,
        crop=None,
        ollama_url="o",
        qdrant_url="q",
        rag_url="r",
        ai_url="a",
        collection="sahool_agri_kb",
        qdrant_api_key="secret",
        expected_ollama_version="0.32.5",
        chat_model="llama3.2:3b",
        embed_model="nomic-embed-text",
        hybrid_query="q",
        require_generation=True,
        timeout_s=1,
    )
    assert result["status"] == "EVIDENCE_REQUIRED"
    assert result["read_only"] is True
    assert result["audit_write_requested"] is False
    assert any(
        c["name"] == "grounded_generation" and c["status"] == "EVIDENCE_REQUIRED"
        for c in result["checks"]
    )


def test_certification_fails_if_hybrid_is_dense_only(monkeypatch):
    m = mod()

    # Reuse a compact fake and intentionally report bm25=0 for the real query.
    def req(method, url, payload=None, headers=None, timeout_s=20.0):
        if url.endswith("/api/version"):
            return m.HTTPResult(200, {"version": "0.32.5"}, "")
        if url.endswith("/v1/models"):
            return m.HTTPResult(
                200, {"data": [{"id": "llama3.2:3b"}, {"id": "nomic-embed-text"}]}, ""
            )
        if url.endswith("/api/embeddings"):
            return m.HTTPResult(200, {"embedding": [1, 2, 3]}, "")
        if url.endswith("/v1/chat/completions"):
            return m.HTTPResult(200, {"choices": [{"message": {"content": "ok"}}]}, "")
        if "/collections/" in url:
            return (
                m.HTTPResult(200, _ok_qdrant(), "")
                if (headers or {}).get("api-key") == "secret"
                else m.HTTPResult(401, {}, "")
            )
        if url.endswith("/readyz"):
            return m.HTTPResult(
                200,
                {
                    "status": "ready",
                    "embedding_contract_parity": True,
                    "collection_vector_schema_parity": True,
                    "sparse_index_hydrated": True,
                    "sparse_index_count": 10,
                    "vector_size": 3,
                },
                "",
            )
        if url.endswith("/v1/search"):
            if payload["tenant_id"] != "t":
                return m.HTTPResult(403, {}, "")
            return m.HTTPResult(
                200,
                {
                    "annotations": [
                        {
                            "chunk_id": "x",
                            "retrieval": {
                                "dense_score": 0.9,
                                "bm25_score": 0.0,
                                "fused_score": 0.6,
                            },
                        }
                    ]
                },
                "",
            )
        if url.endswith("/healthz/ai-provider"):
            return m.HTTPResult(
                200,
                {
                    "generation_enabled": False,
                    "provider": "local",
                    "provider_class": "local",
                    "available": True,
                    "model": "llama3.2:3b",
                    "wire_format": "openai_chat",
                },
                "",
            )
        raise AssertionError(url)

    monkeypatch.setattr(m, "_request", req)
    result = m.certify(
        tenant_id="t",
        field_id=None,
        crop=None,
        ollama_url="o",
        qdrant_url="q",
        rag_url="r",
        ai_url="a",
        collection="sahool_agri_kb",
        qdrant_api_key="secret",
        expected_ollama_version="0.32.5",
        chat_model="llama3.2:3b",
        embed_model="nomic-embed-text",
        hybrid_query="q",
        require_generation=False,
        timeout_s=1,
    )
    assert result["status"] == "FAIL"
    assert any(c["name"] == "rag_hybrid_query" and c["status"] == "FAIL" for c in result["checks"])


@pytest.fixture
def published_facts(monkeypatch):
    """Exercise the real advisor publication boundary, with no provider or DB I/O."""
    from unittest.mock import AsyncMock

    import httpx

    from services.ai_agronomist import ai_evidence_runtime as runtime
    from services.ai_agronomist.ai_generation import GenResult
    from services.ai_agronomist.main import AdvisorQuery
    from shared.ai.structured_advisory import digest, preview_advisory
    from tests_v9.test_b6m4_structured_advisory import FIELD, TENANT, document, state

    canonical = state()
    model_text = json.dumps(document(canonical))
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", AsyncMock(return_value=canonical))
    monkeypatch.setattr(runtime, "_generation_allowed", lambda _: True)
    monkeypatch.setattr(runtime.ai_generation, "resolve_generation", lambda _: None)
    monkeypatch.setattr(
        runtime.policy_envelope, "gate_generation", lambda *a, **k: {"decision": "allowed"}
    )
    monkeypatch.setattr(
        runtime.ai_generation,
        "generate",
        AsyncMock(return_value=GenResult(text=model_text, model="llama3.2:3b", provider="local")),
    )
    client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={"annotations": [{"chunk_id": "seed:1", "text": "مرجع القمح"}], "edges": []},
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(transport=transport, **kw))

    async def record(**kwargs):
        validation = await preview_advisory(
            kwargs["model_output"],
            tenant_id=kwargs["tenant_id"],
            field_id=kwargs["field_id"],
            state=canonical,
            candidates=[],
        )
        return {
            "persisted": True,
            "advisory_validation": {
                "status": "verified",
                "model_output_digest": digest(kwargs["model_output"]),
                **validation,
            },
        }

    monkeypatch.setattr(runtime, "_record_ai_advice_event", record)
    return asyncio.run(
        runtime.build_evidence_response(
            AdvisorQuery(question="ما قياسات الحقل؟", field_id=FIELD),
            endpoint_mode="chat",
            x_tenant_id=TENANT,
            save_agent_tool_audit=lambda _: None,
            save_pending_approval=lambda _: None,
        )
    )


def _certify_generation(monkeypatch, response):
    m = mod()

    def req(method, url, payload=None, headers=None, timeout_s=20.0):
        bodies = {
            "/api/version": {"version": "0.32.5"},
            "/v1/models": {"data": [{"id": "llama3.2:3b"}, {"id": "nomic-embed-text"}]},
            "/api/embeddings": {"embedding": [1, 2, 3]},
            "/v1/chat/completions": {"choices": [{"message": {"content": "ok"}}]},
            "/readyz": {
                "status": "ready",
                "embedding_contract_parity": True,
                "collection_vector_schema_parity": True,
                "sparse_index_hydrated": True,
                "sparse_index_count": 10,
            },
            "/healthz/ai-provider": {
                "generation_enabled": True,
                "provider": "local",
                "provider_class": "local",
                "available": True,
                "model": "llama3.2:3b",
                "wire_format": "openai_chat",
            },
        }
        if url.endswith("/v1/chat"):
            return m.HTTPResult(200, response, "")
        if "/collections/" in url:
            return (
                m.HTTPResult(200, _ok_qdrant(), "")
                if (headers or {}).get("api-key") == "secret"
                else m.HTTPResult(401, {}, "")
            )
        if url.endswith("/v1/search"):
            if payload["tenant_id"] != response["tenant_id"]:
                return m.HTTPResult(403, {}, "")
            return m.HTTPResult(
                200,
                {
                    "annotations": [
                        {"chunk_id": "seed:1", "retrieval": {"dense_score": 1, "bm25_score": 1}}
                    ]
                },
                "",
            )
        for suffix, body in bodies.items():
            if url.endswith(suffix):
                return m.HTTPResult(200, body, "")
        raise AssertionError((method, url))

    monkeypatch.setattr(m, "_request", req)
    return m.certify(
        tenant_id=response["tenant_id"],
        field_id=response["field_id"],
        crop=None,
        ollama_url="http://ollama",
        qdrant_url="http://qdrant",
        rag_url="http://rag",
        ai_url="http://ai",
        collection="sahool_agri_kb",
        qdrant_api_key="secret",
        expected_ollama_version="0.32.5",
        chat_model="llama3.2:3b",
        embed_model="nomic-embed-text",
        hybrid_query="القمح GDD",
        require_generation=True,
        timeout_s=1,
    )


def test_grounded_certification_accepts_the_actual_published_fact_contract(
    monkeypatch, published_facts
):
    result = _certify_generation(monkeypatch, published_facts)
    assert result["status"] == "PASS"
    assert result["read_only"] is False
    assert result["audit_write_requested"] is True
    assert result["audit_write_scope"] == "advisor_chat"
    check = next(c for c in result["checks"] if c["name"] == "grounded_generation")
    assert check["evidence"]["generation_surfaced"] is True
    assert check["evidence"]["generation_attempted_provider"] == "local"
    assert check["evidence"]["generation_attempted_model"] == "llama3.2:3b"


@pytest.mark.parametrize(
    "updates",
    [
        {
            "mode": "generated_grounded",
            "generation_status": "succeeded",
            "guardrail_result": {"status": "not_executed"},
        },
        {"mode": "evidence_only"},
        {"generation_status": "suppressed_unvalidated_output"},
        {"generation_status": "suppressed_ungrounded"},
        {"generation_status": "attempted_failed"},
        {"generation_status": "blocked_by_policy"},
        {"generation_status": "not_attempted"},
        {"generation_surfaced": False},
        {"generation_surfaced": "true"},
        {"generation_surfaced": None},
        {"generation_provider": None, "generation_model": None},
        {"generation_provider": "external"},
        {"generation_model": "another-model"},
        {"generation_attempted_provider": None},
        {"generation_attempted_model": "another-model"},
        {"annotations": {"rag": []}},
        {"guardrail_result": {"status": "not_executed"}},
        {"advisory_validation": {"status": "blocked"}},
        {"audit_event": {"persisted": False}},
    ],
)
def test_grounded_certification_rejects_attempts_fallbacks_and_invalid_receipts(
    monkeypatch, published_facts, updates
):
    response = copy.deepcopy(published_facts)
    response.update(updates)
    result = _certify_generation(monkeypatch, response)
    assert result["status"] == "FAIL"
    # Even a rejected answer follows a chat request that can have persisted an audit.
    assert result["read_only"] is False
    assert result["audit_write_requested"] is True
    assert any(
        c["name"] == "grounded_generation" and c["status"] == "FAIL" for c in result["checks"]
    )


@pytest.mark.parametrize("require_generation", [False, True])
def test_harness_failure_does_not_claim_a_possible_audit_write_was_read_only(
    monkeypatch, capsys, require_generation
):
    m = mod()

    def unavailable(**kwargs):
        raise TimeoutError("response unavailable; persistence cannot be inferred")

    monkeypatch.setattr(m, "certify", unavailable)
    args = ["--tenant-id", "tenant-a", "--field-id", "field-a"]
    if require_generation:
        args.append("--require-generation")
    assert m.main(args) == 4
    result = json.loads(capsys.readouterr().out)
    assert result["read_only"] is (not require_generation)
    assert result["audit_write_requested"] is (None if require_generation else False)
    assert result["audit_write_scope"] == ("advisor_chat" if require_generation else None)
