from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_vllm_rejects_stale_global_ai_model(monkeypatch):
    cfgmod = _load("services/sahool-platform/api/ai_provider_config.py", "delta_cfg")
    gen = _load("services/ai_agronomist/ai_generation.py", "delta_gen")
    monkeypatch.setenv("AI_PROVIDER", "vllm")
    monkeypatch.setenv("AI_MODEL", "qwen3")
    monkeypatch.setenv("VLLM_MODEL", "jais-natural-farmer")
    assert cfgmod.resolve_ai_provider().model == "jais-natural-farmer"
    assert gen.resolve_generation().model == "jais-natural-farmer"


def test_local_ollama_contract_is_bootstrap_aligned_openai_chat(monkeypatch):
    cfgmod = _load("services/sahool-platform/api/ai_provider_config.py", "delta_cfg_local")
    gen = _load("services/ai_agronomist/ai_generation.py", "delta_gen_local")
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("AI_MODELS", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)
    a = cfgmod.resolve_ai_provider()
    b = gen.resolve_generation()
    assert a.model == b.model == "llama3.2:3b"
    assert a.wire_format == b.wire_format == "openai_chat"
    assert a.base_url == "http://sahool-ollama:11434/v1"
    assert b.endpoint == "http://sahool-ollama:11434/v1/chat/completions"
    assert a.endpoint.endswith("/v1/chat/completions")


def test_local_ai_rag_passes_qdrant_api_key_to_both_clients():
    source = (ROOT / "services/local-ai-rag/main.py").read_text(encoding="utf-8")
    assert 'QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None' in source
    assert "QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY" in source
    assert (
        "api_key=QDRANT_API_KEY" in source.split("QdrantVectorStore.from_existing_collection", 1)[1]
    )
    assert '_GLOBAL_REFERENCE_TENANT = "__global__"' in source
    assert "MatchAny(any=[tenant_id, _GLOBAL_REFERENCE_TENANT])" in source
    assert "global reference tenant is reserved for curated seed ingestion" in source


def test_seed_writes_canonical_payload_and_fails_required_embedding_closed():
    source = (ROOT / "services/qdrant-seed/seed.py").read_text(encoding="utf-8")
    assert '"page_content": doc["text"]' in source
    assert (
        'SEED_TENANT_ID = (os.getenv("QDRANT_SEED_TENANT_ID") or "__seed_quarantine__").strip()'
        in source
    )
    assert (
        "global reference seed requires QDRANT_SEED_PROVENANCE_FILE or QDRANT_SEED_PROVENANCE_JSON"
        in source
    )
    assert '"tenant_id": SEED_TENANT_ID' in source
    assert '"chunk_id": chunk_id' in source
    assert '"prescriptive_eligible": False' in source
    assert 'raise RuntimeError("required Qdrant seed embedding failed") from e' in source


def test_dense_sparse_fusion_uses_canonical_chunk_id_and_survives_restart():
    sys.path.insert(0, str(ROOT / "services/sahool-platform"))
    from core.rag.production_qdrant import (
        HashEmbeddingProvider,
        HybridQdrantRetriever,
        KnowledgeChunk,
    )

    class UUIDQdrant:
        vector_size = 32

        def __init__(self):
            self.points = {}

        def ensure_collection(self, *, vector_size=None):
            assert vector_size == 32

        def upsert(self, chunks, embeddings):
            for chunk, vector in zip(chunks, embeddings, strict=True):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sahool-rag:{chunk.chunk_id}"))
                self.points[point_id] = (chunk.payload, vector)

        def search(self, vector, *, tenant_id, filters=None, limit=12):
            rows = []
            for point_id, (payload, stored) in self.points.items():
                meta = payload["metadata"]
                if meta["tenant_id"] != tenant_id:
                    continue
                score = sum(a * b for a, b in zip(vector, stored, strict=True))
                rows.append((point_id, score, payload))
            return rows[:limit]

        def scroll_payloads(self, *, page_size=256, max_pages=10000):
            return [(pid, payload) for pid, (payload, _v) in self.points.items()]

        def collection_point_count(self):
            return len(self.points)

    q = UUIDQdrant()
    emb = HashEmbeddingProvider(32)
    text = "wheat irrigation salinity management"
    chunk = KnowledgeChunk(
        chunk_id="wheat-001",
        tenant_id="tenant-a",
        text=text,
        source_type="curated_reference",
        document_id="doc-1",
        chunk_index=0,
        total_chunks=1,
        metadata={
            "evidence_level": "document",
            "crop": "wheat",
            "source_class": "curated_reference",
            "publisher": "test publisher",
            "source_uri": "https://example.invalid/wheat",
            "source_revision": "r1",
            "license": "test-only",
        },
    )
    first = HybridQdrantRetriever(q, emb)
    assert first.ingest([chunk]) == 1
    row = first.retrieve("wheat irrigation", tenant_id="tenant-a", final_k=1)[0]
    assert row.chunk.chunk_id == "wheat-001"
    assert row.dense_score > 0 and row.bm25_score > 0

    restarted = HybridQdrantRetriever(q, emb)
    report = restarted.rebuild_sparse_index()
    # التقريرُ اكتسب حقولَ تشخيصٍ (`RAG-CORPUS-MEASUREMENT-INTEGRITY-01`)، فالمساواةُ
    # التامّة صارت تقيس **شكلَ التقرير** لا العدّ الذي وُجِد الاختبار لأجله. تُقاس
    # الأعدادُ صراحةً، ويُقاس أنّ حقول الرفض **فارغة** — وهو تأكيدٌ أقوى من قبلُ.
    assert report["total_points"] == 1
    assert report["loaded_chunks"] == 1
    assert report["skipped_points"] == 0
    assert report["skipped_by_reason"] == {}
    assert report["skipped_samples"] == {}
    row2 = restarted.retrieve("wheat irrigation", tenant_id="tenant-a", final_k=1)[0]
    assert row2.chunk.chunk_id == "wheat-001"
    assert row2.dense_score > 0 and row2.bm25_score > 0


def test_rag_reference_chunk_cannot_claim_prescriptive_authority():
    sys.path.insert(0, str(ROOT / "services/sahool-platform"))
    from core.rag.production_qdrant import KnowledgeChunk

    with pytest.raises(ValueError, match="cannot be prescriptive"):
        KnowledgeChunk(
            chunk_id="bad",
            tenant_id="t",
            text="apply X",
            source_type="forum",
            document_id="d",
            chunk_index=0,
            total_chunks=1,
            metadata={"evidence_level": "document", "prescriptive_eligible": True},
        )


def test_reference_provenance_is_carried_to_annotation_without_authority():
    sys.path.insert(0, str(ROOT / "services/sahool-platform"))
    from core.rag.production_qdrant import KnowledgeChunk, ReferenceProvenance, RetrievedAnnotation

    text = "FAO reference guidance"
    provenance = ReferenceProvenance(
        publisher="FAO",
        source_uri="https://www.fao.org/example",
        source_revision="2026-08",
        license="reference-use",
        citation="FAO example",
        jurisdiction="YE",
        language="ar",
        agrovoc_concept_ids=("c_7951", "c_7951"),
    )
    chunk = KnowledgeChunk(
        chunk_id="fao-1",
        tenant_id="tenant-a",
        text=text,
        source_type="official_reference",
        document_id="fao-doc",
        chunk_index=0,
        total_chunks=1,
        metadata=provenance.metadata(text=text),
    )
    annotation = RetrievedAnnotation(chunk, 0.8, 0.4, 0.68).as_annotation()
    assert annotation["publisher"] == "FAO"
    assert annotation["source_revision"] == "2026-08"
    assert annotation["decision_authority"] == "none"
    assert annotation["retrieval"] == {
        "dense_score": 0.8,
        "bm25_score": 0.4,
        "fused_score": 0.68,
        "rerank_score": None,
    }
    assert chunk.payload["metadata"]["prescriptive_eligible"] is False
    assert chunk.payload["metadata"]["agrovoc_concept_ids"] == ["c_7951"]


def test_qdrant_search_scope_is_current_tenant_or_global_reference_only():
    sys.path.insert(0, str(ROOT / "services/sahool-platform"))
    from core.rag.production_qdrant import QdrantHttpClient

    class Capture(QdrantHttpClient):
        def __init__(self):
            super().__init__("http://qdrant", "kb", 32, "secret")
            self.payload = None

        def _request(self, method, path, payload=None):
            self.payload = payload
            return {"result": []}

    client = Capture()
    client.search([0.0] * 32, tenant_id="tenant-a", filters={"crop": "wheat"})
    must = client.payload["filter"]["must"]
    assert must[0] == {
        "key": "metadata.tenant_id",
        "match": {"any": ["tenant-a", "__global__"]},
    }
    assert {"key": "metadata.crop", "match": {"value": "wheat"}} in must


def test_global_reference_is_visible_but_other_tenant_data_is_not():
    sys.path.insert(0, str(ROOT / "services/sahool-platform"))
    from core.rag.production_qdrant import BM25Index, KnowledgeChunk

    idx = BM25Index()
    idx.add(
        KnowledgeChunk(
            chunk_id="global",
            tenant_id="__global__",
            text="wheat irrigation",
            source_type="official_reference",
            document_id="g",
            chunk_index=0,
            total_chunks=1,
            metadata={
                "evidence_level": "document",
                "source_class": "official_reference",
                "publisher": "test publisher",
                "source_uri": "https://example.invalid/global",
                "source_revision": "r1",
                "license": "test-only",
                "prescriptive_eligible": False,
            },
        )
    )
    idx.add(
        KnowledgeChunk(
            chunk_id="private-b",
            tenant_id="tenant-b",
            text="wheat irrigation private",
            source_type="uploaded_document",
            document_id="b",
            chunk_index=0,
            total_chunks=1,
            metadata={
                "evidence_level": "document",
                "source_uri": "tenant-upload://tenant-b/b",
                "source_revision": "sha256:file-b",
            },
        )
    )
    rows = idx.search("wheat irrigation", tenant_id="tenant-a")
    assert [chunk.chunk_id for chunk, _score in rows] == ["global"]

    with pytest.raises(ValueError, match="explicitly classified reference"):
        KnowledgeChunk(
            chunk_id="bad-global",
            tenant_id="__global__",
            text="secret",
            source_type="upload",
            document_id="x",
            chunk_index=0,
            total_chunks=1,
            metadata={"evidence_level": "document"},
        )


def test_compose_env_keeps_ollama_and_qdrant_identity_aligned():
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    expected_image = "ollama/ollama:0.32.5@sha256:4dea9fb511947e24a84237bb636b0203abcb2ff0d3fbc7b4ff865deb91362131"
    assert f"OLLAMA_IMAGE={expected_image}" in env
    ollama_section = compose.split("\n  sahool-ollama:\n", 1)[1].split(
        "\n  sahool-vllm-jais:\n", 1
    )[0]
    assert f"image: ${{OLLAMA_IMAGE:-{expected_image}}}" in ollama_section
    assert "ports:" not in ollama_section
    assert "OLLAMA_BASE_URL=http://sahool-ollama:11434" in env
    assert "QDRANT_COLLECTION=sahool_agri_kb" in env
    assert "QDRANT_SEED_TENANT_ID=__seed_quarantine__" in env
    local_section = compose.split("\n  sahool-local-ai-rag:\n", 1)[1].split(
        "\n  sahool-rag-retrieval:\n", 1
    )[0]
    retrieval_section = compose.split("\n  sahool-rag-retrieval:\n", 1)[1].split(
        "\n  sahool-knowledge-graph:\n", 1
    )[0]
    seed_section = compose.split("\n  sahool-qdrant-seed:\n", 1)[1].split(
        "\n  sahool-erp-bridge:\n", 1
    )[0]
    assert "COLLECTION_NAME: ${QDRANT_COLLECTION:-sahool_agri_kb}" in local_section
    assert "QDRANT_COLLECTION: ${QDRANT_COLLECTION:-sahool_agri_kb}" in retrieval_section
    assert "COLLECTION_NAME: ${QDRANT_COLLECTION:-sahool_agri_kb}" in seed_section
    assert "QDRANT_SEED_TENANT_ID: ${QDRANT_SEED_TENANT_ID:-__seed_quarantine__}" in seed_section


def test_global_reference_ingest_is_reserved_in_canonical_rag_service():
    source = (ROOT / "services/rag-retrieval/main.py").read_text(encoding="utf-8")
    assert "GLOBAL_REFERENCE_INGEST_RESERVED" in source
    assert "GLOBAL_REFERENCE_TENANT_RESERVED" in source
    assert "if tenant_id == GLOBAL_REFERENCE_TENANT" in source


def test_bm25_upsert_replaces_sparse_document_frequency_contribution():
    sys.path.insert(0, str(ROOT / "services/sahool-platform"))
    from core.rag.production_qdrant import BM25Index, KnowledgeChunk

    def chunk(text: str) -> KnowledgeChunk:
        return KnowledgeChunk(
            chunk_id="same",
            tenant_id="tenant-a",
            text=text,
            source_type="uploaded_document",
            document_id="doc",
            chunk_index=0,
            total_chunks=1,
            metadata={
                "evidence_level": "document",
                "source_uri": "tenant-upload://tenant-a/doc",
                "source_revision": "sha256:test-file",
            },
        )

    idx = BM25Index()
    idx.add(chunk("wheat legacyterm"))
    idx.add(chunk("maize replacementterm"))

    assert len(idx) == 1
    assert "legacyterm" not in idx.doc_freq
    assert idx.doc_freq["maize"] == 1
    assert idx.doc_freq["replacementterm"] == 1
    assert idx.search("legacyterm", tenant_id="tenant-a") == []
    rows = idx.search("replacementterm", tenant_id="tenant-a")
    assert [row[0].chunk_id for row in rows] == ["same"]


def test_ollama_runtime_probe_contract_is_read_only_and_version_pinned(monkeypatch):
    probe_path = ROOT / "scripts/ci/ollama_runtime_probe.py"
    spec = importlib.util.spec_from_file_location("ollama_runtime_probe", probe_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    calls = []

    def fake_request(base_url, path, *, payload=None, timeout_s=20.0):
        calls.append((path, payload))
        if path == "/api/version":
            return {"version": "0.32.5"}
        if path == "/v1/models":
            return {"data": [{"id": "llama3.2:3b"}, {"id": "nomic-embed-text:latest"}]}
        if path == "/api/embeddings":
            return {"embedding": [0.1, 0.2, 0.3]}
        if path == "/v1/chat/completions":
            return {"choices": [{"message": {"content": "SAHOOL_OK"}}]}
        raise AssertionError(path)

    monkeypatch.setattr(module, "_request_json", fake_request)
    checks, evidence = module.probe(
        base_url="http://sahool-ollama:11434",
        expected_version="0.32.5",
        chat_model="llama3.2:3b",
        embed_model="nomic-embed-text",
        smoke=True,
        timeout_s=1.0,
    )
    assert all(check.ok for check in checks)
    assert evidence["embedding_dimensions"] == 3
    assert [path for path, _ in calls] == [
        "/api/version",
        "/v1/models",
        "/api/embeddings",
        "/v1/chat/completions",
    ]
    # Certification is observational/inference-only: no model pull/create/copy/delete endpoint.
    assert not any(
        path in {"/api/pull", "/api/create", "/api/copy", "/api/delete"} for path, _ in calls
    )


def test_ollama_runtime_probe_fails_version_mismatch(monkeypatch):
    probe_path = ROOT / "scripts/ci/ollama_runtime_probe.py"
    spec = importlib.util.spec_from_file_location("ollama_runtime_probe_mismatch", probe_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    def fake_request(base_url, path, *, payload=None, timeout_s=20.0):
        if path == "/api/version":
            return {"version": "0.32.4"}
        if path == "/v1/models":
            return {"data": [{"id": "llama3.2:3b"}, {"id": "nomic-embed-text"}]}
        raise AssertionError(path)

    monkeypatch.setattr(module, "_request_json", fake_request)
    checks, _ = module.probe(
        base_url="http://sahool-ollama:11434",
        expected_version="0.32.5",
        chat_model="llama3.2:3b",
        embed_model="nomic-embed-text",
        smoke=False,
        timeout_s=1.0,
    )
    version = next(check for check in checks if check.name == "version")
    assert version.ok is False
