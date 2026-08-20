from __future__ import annotations

import importlib.util
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
                    "collection_schema_parity": True,
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
                    "collection_schema_parity": True,
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
                    "collection_schema_parity": True,
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
