from __future__ import annotations

import os
import urllib.request
from typing import Any

from core.rag.production_qdrant import (
    HashEmbeddingProvider,
    HybridQdrantRetriever,
    KnowledgeChunk,
    QdrantHttpClient,
)
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

app = FastAPI(title="SAHOOL Production RAG Retrieval", version="2026.2")
QDRANT_URL = os.getenv("QDRANT_URL", "http://sahool-qdrant:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "sahool_agri_kb")
VECTOR_SIZE = int(os.getenv("EMBEDDING_DIM", "384"))
_retriever = HybridQdrantRetriever(
    QdrantHttpClient(QDRANT_URL, COLLECTION, VECTOR_SIZE, os.getenv("QDRANT_API_KEY") or None),
    HashEmbeddingProvider(VECTOR_SIZE),
)


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
            f'sahool_rag_retrieval_info{{collection="{COLLECTION}",vector_size="{VECTOR_SIZE}"}} 1',
            "",
        ]
    )
    return Response(content=body, media_type="text/plain; version=0.0.4")


@app.get("/readyz")
async def readyz():
    try:
        req = urllib.request.Request(f"{QDRANT_URL.rstrip('/')}/collections")
        if os.getenv("QDRANT_API_KEY"):
            req.add_header("api-key", os.getenv("QDRANT_API_KEY", ""))
        urllib.request.urlopen(req, timeout=3).read()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"qdrant not ready: {exc}") from exc
    return {
        "status": "ready",
        "service": "rag-retrieval",
        "qdrant_url": QDRANT_URL,
        "collection": COLLECTION,
    }


@app.post("/ingest")
async def ingest(req: IngestRequest):
    chunks = [KnowledgeChunk(**c.model_dump()) for c in req.chunks]
    try:
        return {"ingested": _retriever.ingest(chunks)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc


@app.post("/search")
async def search(req: SearchRequest):
    filters = {
        "crop": req.crop,
        "field_id": req.field_id,
        "region": req.region,
        "source_type": req.source_type,
    }
    rows = _retriever.retrieve(
        req.query, tenant_id=req.tenant_id, filters=filters, final_k=req.final_k
    )
    return {"annotations": [r.as_annotation() for r in rows]}
