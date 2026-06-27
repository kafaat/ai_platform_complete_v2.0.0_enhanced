"""Hybrid RAG retrieval primitives for SAHOOL.

This module closes the remaining RAG gap without giving RAG decision authority.
It provides: Dense+BM25 score fusion, adjacent chunk expansion, reranking, and
strict tenant/metadata filtering. Results are knowledge annotations only; they
must pass through Field Context Coordinator -> Canonical Field State annotations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    tenant_id: str
    document_id: str
    chunk_index: int
    total_chunks: int
    text: str
    metadata: dict[str, object] = field(default_factory=dict)
    dense_score: float = 0.0
    sparse_score: float = 0.0

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("RAG chunk must include tenant_id")
        if "evidence_level" not in self.metadata:
            raise ValueError("RAG chunk must include evidence_level metadata")
        if self.metadata.get("evidence_level") == "lab":
            raise ValueError("RAG cannot claim lab evidence; use lab_state only")


@dataclass(frozen=True)
class RetrievalResult:
    chunk: RagChunk
    fused_score: float
    rerank_score: float | None = None
    role: Literal["hit", "neighbor"] = "hit"

    @property
    def annotation(self) -> dict[str, object]:
        return {
            "type": "rag_annotation",
            "source": self.chunk.document_id,
            "chunk_id": self.chunk.chunk_id,
            "section": self.chunk.metadata.get("section"),
            "page": self.chunk.metadata.get("page"),
            "evidence_level": self.chunk.metadata.get("evidence_level"),
            "text": self.chunk.text,
            "score": self.rerank_score if self.rerank_score is not None else self.fused_score,
            "verified": False,
        }


def _metadata_match(chunk: RagChunk, filters: dict[str, object]) -> bool:
    for key, value in filters.items():
        if value is None:
            continue
        if key == "tenant_id":
            if chunk.tenant_id != value:
                return False
        elif chunk.metadata.get(key) != value:
            return False
    return True


def reciprocal_rank_fusion(
    dense_ranked: list[RagChunk],
    sparse_ranked: list[RagChunk],
    *,
    dense_weight: float = 0.7,
    sparse_weight: float = 0.3,
    k: int = 60,
) -> list[RetrievalResult]:
    """Fuse dense and sparse rankings with weighted RRF.

    Weighted RRF is deterministic and avoids over-trusting one retriever.
    """
    scores: dict[str, float] = {}
    chunks: dict[str, RagChunk] = {}
    for rank, chunk in enumerate(dense_ranked, start=1):
        chunks[chunk.chunk_id] = chunk
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + dense_weight / (k + rank)
    for rank, chunk in enumerate(sparse_ranked, start=1):
        chunks[chunk.chunk_id] = chunk
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + sparse_weight / (k + rank)
    return [
        RetrievalResult(chunk=chunks[cid], fused_score=score)
        for cid, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


def expand_adjacent_chunks(
    hits: list[RetrievalResult],
    corpus: list[RagChunk],
    *,
    window: int = 1,
) -> list[RetrievalResult]:
    """Include ±N neighboring chunks from the same document.

    Neighbor chunks are annotations only and receive a lower score than direct hits.
    """
    by_doc_index = {(c.document_id, c.chunk_index): c for c in corpus}
    seen = {h.chunk.chunk_id for h in hits}
    out = list(hits)
    for hit in hits:
        for delta in range(-window, window + 1):
            if delta == 0:
                continue
            neighbor = by_doc_index.get((hit.chunk.document_id, hit.chunk.chunk_index + delta))
            if neighbor is None or neighbor.chunk_id in seen:
                continue
            seen.add(neighbor.chunk_id)
            out.append(
                RetrievalResult(
                    chunk=neighbor,
                    fused_score=hit.fused_score * 0.65,
                    role="neighbor",
                )
            )
    return out


def simple_rerank(query: str, results: list[RetrievalResult]) -> list[RetrievalResult]:
    """Deterministic lexical reranker fallback.

    A production deployment may replace this with BGE/CrossEncoder, but the
    interface and tests stay stable.
    """
    terms = {t.strip().lower() for t in query.split() if len(t.strip()) > 1}
    reranked: list[RetrievalResult] = []
    for result in results:
        text = result.chunk.text.lower()
        overlap = sum(1 for term in terms if term in text)
        score = result.fused_score + (overlap * 0.05)
        reranked.append(
            RetrievalResult(
                chunk=result.chunk,
                fused_score=result.fused_score,
                rerank_score=round(score, 6),
                role=result.role,
            )
        )
    return sorted(reranked, key=lambda r: r.rerank_score or r.fused_score, reverse=True)


def hybrid_retrieve(
    *,
    query: str,
    dense_ranked: list[RagChunk],
    sparse_ranked: list[RagChunk],
    corpus: list[RagChunk],
    tenant_id: str,
    metadata_filters: dict[str, object] | None = None,
    top_k: int = 5,
) -> list[RetrievalResult]:
    """Run safe hybrid retrieval for one tenant.

    All returned objects are RAG annotations and cannot become recommendations.
    """
    filters = {**(metadata_filters or {}), "tenant_id": tenant_id}
    dense = [c for c in dense_ranked if _metadata_match(c, filters)]
    sparse = [c for c in sparse_ranked if _metadata_match(c, filters)]
    filtered_corpus = [c for c in corpus if _metadata_match(c, filters)]
    fused = reciprocal_rank_fusion(dense, sparse)
    expanded = expand_adjacent_chunks(fused[: max(top_k * 2, top_k)], filtered_corpus, window=1)
    reranked = simple_rerank(query, expanded)
    return reranked[:top_k]
