from __future__ import annotations

import os
from typing import Any

from core.rag.production_qdrant import (
    GLOBAL_REFERENCE_TENANT,
    HybridQdrantRetriever,
    KnowledgeChunk,
    OllamaEmbeddingProvider,
    QdrantHttpClient,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from shared.security.gateway_deps import require_service_token
from shared.security.trusted_tenant import TrustedTenantError, resolve_trusted_tenant

app = FastAPI(title="SAHOOL Production RAG Retrieval", version="2026.2")
QDRANT_URL = os.getenv("QDRANT_URL", "http://sahool-qdrant:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "sahool_agri_kb")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://sahool-ollama:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
_embedding_provider = OllamaEmbeddingProvider(OLLAMA_BASE_URL, EMBEDDING_MODEL)
_qdrant = QdrantHttpClient(QDRANT_URL, COLLECTION, 0, os.getenv("QDRANT_API_KEY") or None)
_retriever = HybridQdrantRetriever(_qdrant, _embedding_provider)
_sparse_ready = False
_sparse_report: dict[str, int] = {"total_points": 0, "loaded_chunks": 0, "skipped_points": 0}


def _ensure_sparse_index(*, force: bool = False) -> dict[str, int]:
    """Hydrate deterministic BM25 from canonical Qdrant payloads exactly once per process.

    Readiness fails closed if any stored point cannot be reconstructed; otherwise a
    restart would silently advertise hybrid retrieval while serving dense-only.
    """
    global _sparse_ready, _sparse_report
    if _sparse_ready and not force:
        return _sparse_report
    report = _retriever.rebuild_sparse_index()
    live_count = _qdrant.collection_point_count()
    if report["total_points"] != live_count:
        raise ValueError(
            f"Qdrant scroll/count mismatch: scroll={report['total_points']} count={live_count}"
        )
    if report["skipped_points"]:
        raise ValueError(
            f"canonical sparse rebuild skipped {report['skipped_points']} Qdrant points"
        )
    _sparse_report = report
    _sparse_ready = True
    return report


class ChunkIn(BaseModel):
    chunk_id: str
    tenant_id: str
    text: str
    source_type: str
    document_id: str
    chunk_index: int
    total_chunks: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    chunks: list[ChunkIn]


class SearchRequest(BaseModel):
    tenant_id: str
    query: str
    crop: str | None = None
    field_id: str | None = None
    region: str | None = None
    source_type: str | None = None
    final_k: int = Field(default=5, ge=1, le=10)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "rag-retrieval"}


@app.get("/metrics")
async def metrics():
    body = "\n".join(
        [
            "# HELP sahool_rag_retrieval_info Static service info",
            "# TYPE sahool_rag_retrieval_info gauge",
            f'sahool_rag_retrieval_info{{collection="{COLLECTION}",embedding_provider="ollama",embedding_model="{EMBEDDING_MODEL}"}} 1',
            "",
        ]
    )
    return Response(content=body, media_type="text/plain; version=0.0.4")


@app.get("/readyz")
async def readyz():
    try:
        # Readiness proves the embedding contract against the *live* Qdrant schema.
        # A reachable Qdrant alone is insufficient: a different vector space makes
        # retrieval operationally wrong while all HTTP probes remain green.
        vector = _embedding_provider.embed("SAHOOL retrieval readiness probe")
        collection_dim = _qdrant.collection_vector_size()
        if len(vector) != collection_dim:
            raise ValueError(
                f"embedding/Qdrant dimension mismatch: embedding={len(vector)} collection={collection_dim}"
            )
        sparse = _ensure_sparse_index()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"rag retrieval not ready: {exc}") from exc
    return {
        "status": "ready",
        "service": "rag-retrieval",
        "qdrant_url": QDRANT_URL,
        "collection": COLLECTION,
        "embedding_provider": "ollama",
        "embedding_model": EMBEDDING_MODEL,
        "vector_size": collection_dim,
        "embedding_contract_parity": True,
        "collection_schema_parity": True,
        "sparse_index_hydrated": True,
        "sparse_index_count": sparse["loaded_chunks"],
    }


@app.post("/v1/ingest")
async def ingest(
    req: IngestRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    _token: None = Depends(require_service_token),
):
    # SEC-4: internal data-plane write. Mirrors knowledge-graph writes — requires the
    # trusted service token (X-Agent-Token == SAHOOL_AGENT_TOKEN), fail-closed 403.
    # C4: RAG ingestion mutates tenant-scoped evidence. The tenant source of truth is
    # the gateway/service header; per-chunk tenant_id values may only echo that header.
    chunks = []
    for c in req.chunks:
        try:
            tenant_id = resolve_trusted_tenant(x_tenant_id, c.tenant_id)
        except TrustedTenantError as exc:
            raise HTTPException(status_code=403, detail=exc.code) from exc
        if tenant_id == GLOBAL_REFERENCE_TENANT:
            raise HTTPException(status_code=403, detail="GLOBAL_REFERENCE_INGEST_RESERVED")
        payload = c.model_dump()
        payload["tenant_id"] = tenant_id
        # Canonical retrieval owns the storage metadata contract. Callers provide
        # source provenance; the retrieval authority supplies the baseline level
        # required by KnowledgeChunk instead of forcing every generation runtime
        # to duplicate storage-specific metadata.
        payload["metadata"].setdefault("evidence_level", "document")
        try:
            chunks.append(KnowledgeChunk(**payload))
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_RAG_PROVENANCE", "message": str(exc)},
            ) from exc
    try:
        ingested = _retriever.ingest(chunks)
        # Qdrant has changed; force the next read/readiness to reconstruct the complete
        # sparse corpus instead of assuming this process saw every historical ingest.
        global _sparse_ready
        _sparse_ready = False
        return {"ingested": ingested}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc


@app.post("/v1/search")
async def search(
    req: SearchRequest, x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")
):
    # SEC-3: the gateway-injected X-Tenant-Id is the ONLY tenant source of truth.
    # The body tenant_id may only echo it; a missing header or a body mismatch
    # fails closed with 403 (prevents cross-tenant retrieval via a spoofed body).
    try:
        tenant_id = resolve_trusted_tenant(x_tenant_id, req.tenant_id)
    except TrustedTenantError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from exc
    if tenant_id == GLOBAL_REFERENCE_TENANT:
        raise HTTPException(status_code=403, detail="GLOBAL_REFERENCE_TENANT_RESERVED")
    try:
        _ensure_sparse_index()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"hybrid sparse index not ready: {exc}") from exc
    filters = {
        "crop": req.crop,
        "field_id": req.field_id,
        "region": req.region,
        "source_type": req.source_type,
    }
    rows = _retriever.retrieve(req.query, tenant_id=tenant_id, filters=filters, final_k=req.final_k)
    return {"annotations": [r.as_annotation() for r in rows]}
