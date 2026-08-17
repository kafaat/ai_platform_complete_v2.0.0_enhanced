"""Production-grade Qdrant + BM25 hybrid retrieval for SAHOOL.

This module is intentionally dependency-light. It talks to Qdrant through its
HTTP API and keeps BM25 as a local deterministic sparse index. RAG output is
always an annotation; it never becomes a governing evidence value and never
emits a recommendation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

_TOKEN_RE = re.compile(r"[\w\u0600-\u06FF\.]+", re.UNICODE)


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    tenant_id: str
    text: str
    source_type: str
    document_id: str
    chunk_index: int
    total_chunks: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required for every RAG chunk")
        if not self.source_type:
            raise ValueError("source_type is required for every RAG chunk")
        evidence_level = self.metadata.get("evidence_level")
        if not evidence_level:
            raise ValueError("evidence_level metadata is required")
        if evidence_level == "lab":
            raise ValueError(
                "RAG chunks cannot claim lab evidence; lab_state is the source of lab evidence"
            )
        if self.metadata.get("tenant_id") not in (None, self.tenant_id):
            raise ValueError("metadata tenant_id must match chunk tenant_id")

    @property
    def payload(self) -> dict[str, Any]:
        """Canonical Qdrant payload, deliberately compatible with LangChain Qdrant.

        ``page_content`` + ``metadata`` are the shared storage contract.  Canonical
        identifiers live inside metadata so the existing local-ai-rag reader can
        consume canonical writes without a second collection or payload migration.
        """
        metadata = dict(self.metadata)
        metadata.update(
            {
                "chunk_id": self.chunk_id,
                "tenant_id": self.tenant_id,
                "source_type": self.source_type,
                "document_id": self.document_id,
                "chunk_index": self.chunk_index,
                "total_chunks": self.total_chunks,
            }
        )
        return {"page_content": self.text, "metadata": metadata}


@dataclass(frozen=True)
class RetrievedAnnotation:
    chunk: KnowledgeChunk
    dense_score: float
    bm25_score: float
    fused_score: float
    rerank_score: float | None = None
    role: str = "hit"

    def as_annotation(self) -> dict[str, Any]:
        return {
            "type": "rag_annotation",
            "verified": False,
            "decision_authority": "none",
            "chunk_id": self.chunk.chunk_id,
            "document_id": self.chunk.document_id,
            "source_type": self.chunk.source_type,
            "evidence_level": self.chunk.metadata.get("evidence_level"),
            "page": self.chunk.metadata.get("page"),
            "section": self.chunk.metadata.get("section"),
            "text": self.chunk.text,
            "score": self.rerank_score if self.rerank_score is not None else self.fused_score,
            "role": self.role,
        }


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if t.strip()]


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashEmbeddingProvider:
    """Deterministic CPU embedding fallback for tests and offline dev.

    Production deployments should replace this with Ollama/OpenAI/BGE embeddings,
    but keeping this fallback prevents ingestion from failing when GPU services
    are not available in development.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for token in tokenize(text):
            h = int(hashlib.blake2b(token.encode("utf-8"), digest_size=8).hexdigest(), 16)
            idx = h % self.dimensions
            sign = 1.0 if (h >> 63) == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [round(v / norm, 8) for v in vec]


class OllamaEmbeddingProvider:
    """Ollama embedding provider using the same model contract as local-ai-rag.

    The vector dimension is intentionally learned from the live embedding response,
    not hard-coded.  This prevents a nominal ``EMBEDDING_DIM`` from claiming
    collection compatibility when the configured Ollama model actually emits a
    different vector space.
    """

    def __init__(self, base_url: str, model: str, timeout_s: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._dimensions: int | None = None

    @property
    def dimensions(self) -> int | None:
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        body = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/embeddings",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 - internal Ollama URL
            data = json.loads(resp.read().decode("utf-8"))
        vector = data.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise ValueError("Ollama embedding response missing non-empty embedding")
        values = [float(x) for x in vector]
        if self._dimensions is None:
            self._dimensions = len(values)
        elif len(values) != self._dimensions:
            raise ValueError(
                f"Ollama embedding dimension changed: expected {self._dimensions}, got {len(values)}"
            )
        return values


class HttpEmbeddingProvider:
    """HTTP embedding provider for production embedding services.

    Expected response: {"embedding": [..]} or {"data":[{"embedding":[..]}]}.
    """

    def __init__(self, endpoint: str, timeout_s: float = 20.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_s = timeout_s

    def embed(self, text: str) -> list[float]:
        body = json.dumps({"input": text}).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 - endpoint is configured internally
            data = json.loads(resp.read().decode("utf-8"))
        if "embedding" in data:
            return [float(x) for x in data["embedding"]]
        if data.get("data"):
            return [float(x) for x in data["data"][0]["embedding"]]
        raise ValueError("Embedding response missing embedding vector")


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs: dict[str, KnowledgeChunk] = {}
        self.term_freqs: dict[str, dict[str, int]] = {}
        self.doc_freq: dict[str, int] = {}
        self.doc_len: dict[str, int] = {}
        self.avg_len = 0.0

    def add(self, chunk: KnowledgeChunk) -> None:
        terms = tokenize(chunk.text)
        tf: dict[str, int] = {}
        for term in terms:
            tf[term] = tf.get(term, 0) + 1
        self.docs[chunk.chunk_id] = chunk
        self.term_freqs[chunk.chunk_id] = tf
        self.doc_len[chunk.chunk_id] = len(terms)
        for term in tf:
            self.doc_freq[term] = self.doc_freq.get(term, 0) + 1
        self.avg_len = sum(self.doc_len.values()) / max(len(self.doc_len), 1)

    def score(self, query: str, chunk_id: str) -> float:
        if chunk_id not in self.docs:
            return 0.0
        n_docs = len(self.docs)
        length = self.doc_len.get(chunk_id, 0) or 1
        score = 0.0
        for term in tokenize(query):
            tf = self.term_freqs.get(chunk_id, {}).get(term, 0)
            if tf == 0:
                continue
            df = self.doc_freq.get(term, 0)
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            denom = tf + self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
            score += idf * (tf * (self.k1 + 1) / denom)
        return round(score, 6)

    def search(
        self, query: str, *, tenant_id: str, filters: dict[str, Any] | None = None, limit: int = 12
    ) -> list[tuple[KnowledgeChunk, float]]:
        filters = filters or {}
        rows: list[tuple[KnowledgeChunk, float]] = []
        for cid, chunk in self.docs.items():
            if chunk.tenant_id != tenant_id:
                continue
            if any(
                value is not None and chunk.metadata.get(key) != value
                for key, value in filters.items()
            ):
                continue
            s = self.score(query, cid)
            if s > 0:
                rows.append((chunk, s))
        return sorted(rows, key=lambda x: x[1], reverse=True)[:limit]


class QdrantHTTPError(RuntimeError):
    """خطأ HTTP من Qdrant يحفظ **رمز الحالة** بدل دفنه في نصّ الرسالة.

    يرث ``RuntimeError`` عمداً: مستهلكون قائمون يلتقطون ``RuntimeError`` فيبقون
    عاملين بلا تعديل، بينما من يحتاج التصنيف يقرأ ``.status``.
    """

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Qdrant HTTP {status}: {body}")
        self.status = status
        self.body = body


class CollectionProbeStatus(str, Enum):
    """نتيجة استجلاء وجود المجموعة — مصنَّفة، لا منطقيّة.

    SILENT-EXCEPTION-HANDLERS-11-01: كان ``ensure_collection`` يلتقط ``RuntimeError``
    عارياً ويُعامله «المجموعة غير موجودة»، بينما ``_request`` يطوي **كلّ** ``HTTPError``
    في ``RuntimeError`` واحد. فمفتاح API خاطئ (401) أو خدمة ساقطة (503) كانا يُقرآن
    «أنشِئ المجموعة»، فيفشل الإنشاء بخطأ ثانٍ مُربِك وقد ضاع السبب الجذريّ.
    """

    EXISTS = "exists"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"


class QdrantHttpClient:
    def __init__(
        self,
        base_url: str,
        collection: str,
        vector_size: int = 384,
        api_key: str | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.vector_size = vector_size
        self.api_key = api_key
        self.timeout_s = timeout_s

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 - internal service URL
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise QdrantHTTPError(exc.code, body) from exc

    def probe_collection(self) -> CollectionProbeStatus:
        """يستجلي وجود المجموعة ويُصنّف الفشل — لا يبتلعه ولا يختزله إلى «غير موجودة»."""
        try:
            self._request("GET", f"/collections/{self.collection}")
            return CollectionProbeStatus.EXISTS
        except QdrantHTTPError as exc:
            if exc.status == 404:
                return CollectionProbeStatus.NOT_FOUND
            if exc.status in (401, 403):
                return CollectionProbeStatus.UNAUTHORIZED
            if exc.status in (408, 429) or exc.status >= 500:
                return CollectionProbeStatus.UNAVAILABLE
            return CollectionProbeStatus.INVALID_RESPONSE
        except json.JSONDecodeError:
            return CollectionProbeStatus.INVALID_RESPONSE
        except urllib.error.URLError:
            # تعذّر الوصول/مهلة شبكة — انقطاع مزوّد لا غياب مجموعة.
            return CollectionProbeStatus.UNAVAILABLE

    def collection_vector_size(self) -> int:
        """Return the live unnamed-vector size; fail closed on unsupported schemas."""
        data = self._request("GET", f"/collections/{self.collection}")
        vectors = (
            data.get("result", {})
            .get("config", {})
            .get("params", {})
            .get("vectors")
        )
        if not isinstance(vectors, dict):
            raise ValueError("Qdrant collection vectors schema missing")
        size = vectors.get("size")
        if not isinstance(size, int) or size <= 0:
            raise ValueError("Qdrant named/invalid vector schema is not supported by this contract")
        return size

    def ensure_collection(self, *, vector_size: int | None = None) -> None:
        """Create only on proven 404 and verify vector-size parity when known."""
        expected = int(vector_size or self.vector_size)
        if expected <= 0:
            raise ValueError("positive vector size is required to create/verify collection")
        status = self.probe_collection()
        if status is CollectionProbeStatus.EXISTS:
            actual = self.collection_vector_size()
            if actual != expected:
                raise ValueError(
                    f"Qdrant vector-size mismatch: collection={actual}, embedding={expected}"
                )
            self.vector_size = expected
            return
        if status is not CollectionProbeStatus.NOT_FOUND:
            raise RuntimeError(
                f"Qdrant collection probe inconclusive ({status.value}) — "
                "لا تُنشأ مجموعة على أساس فشل غير مُصنَّف"
            )
        self.vector_size = expected
        self._request(
            "PUT",
            f"/collections/{self.collection}",
            {
                "vectors": {"size": expected, "distance": "Cosine"},
                "optimizers_config": {"default_segment_number": 2},
            },
        )

    def upsert(self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]) -> None:
        points = []
        for chunk, vector in zip(chunks, embeddings, strict=True):
            # Qdrant point IDs are uint64 or UUID.  External chunk identifiers may
            # be arbitrary strings, so derive a stable UUID while retaining the
            # original chunk_id in metadata.
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sahool-rag:{chunk.chunk_id}"))
            points.append({"id": point_id, "vector": vector, "payload": chunk.payload})
        self._request("PUT", f"/collections/{self.collection}/points?wait=true", {"points": points})

    def search(
        self,
        vector: list[float],
        *,
        tenant_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 12,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        must = [{"key": "metadata.tenant_id", "match": {"value": tenant_id}}]
        for key, value in (filters or {}).items():
            if value is not None:
                must.append({"key": f"metadata.{key}", "match": {"value": value}})
        response = self._request(
            "POST",
            f"/collections/{self.collection}/points/search",
            {"vector": vector, "limit": limit, "with_payload": True, "filter": {"must": must}},
        )
        return [
            (str(row["id"]), float(row.get("score", 0.0)), row.get("payload", {}))
            for row in response.get("result", [])
        ]


class HybridQdrantRetriever:
    def __init__(
        self,
        qdrant: QdrantHttpClient,
        embeddings: EmbeddingProvider | None = None,
        bm25: BM25Index | None = None,
    ) -> None:
        self.qdrant = qdrant
        self.embeddings = embeddings or HashEmbeddingProvider(qdrant.vector_size)
        self.bm25 = bm25 or BM25Index()
        self._chunks: dict[str, KnowledgeChunk] = {}

    def ingest(self, chunks: list[KnowledgeChunk]) -> int:
        for chunk in chunks:
            self.bm25.add(chunk)
            self._chunks[chunk.chunk_id] = chunk
        vectors = [self.embeddings.embed(chunk.text) for chunk in chunks]
        if not vectors:
            return 0
        dimensions = {len(v) for v in vectors}
        if len(dimensions) != 1:
            raise ValueError(f"embedding dimension drift within ingest batch: {sorted(dimensions)}")
        self.qdrant.ensure_collection(vector_size=next(iter(dimensions)))
        self.qdrant.upsert(chunks, vectors)
        return len(chunks)

    def retrieve(
        self,
        query: str,
        *,
        tenant_id: str,
        filters: dict[str, Any] | None = None,
        top_k_initial: int = 12,
        final_k: int = 5,
    ) -> list[RetrievedAnnotation]:
        query_vector = self.embeddings.embed(query)
        dense_rows = self.qdrant.search(
            query_vector, tenant_id=tenant_id, filters=filters, limit=top_k_initial
        )
        dense_map: dict[str, float] = {cid: score for cid, score, _ in dense_rows}
        sparse_rows = self.bm25.search(
            query, tenant_id=tenant_id, filters=filters, limit=top_k_initial
        )
        sparse_map: dict[str, float] = {chunk.chunk_id: score for chunk, score in sparse_rows}
        candidates = set(dense_map) | set(sparse_map)
        fused: list[RetrievedAnnotation] = []
        for cid in candidates:
            chunk = self._chunks.get(cid)
            if chunk is None:
                payload = next((p for qid, _, p in dense_rows if qid == cid), None)
                if not payload:
                    continue
                # Shared LangChain-compatible payload contract.  During EXPAND we
                # also accept the old canonical top-level payload so a partial rollout
                # cannot make previously written points unreadable.
                nested = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                meta = dict(nested)
                text = payload.get("page_content", payload.get("text"))
                chunk_id = meta.get("chunk_id", payload.get("chunk_id", cid))
                tenant = meta.get("tenant_id", payload.get("tenant_id"))
                source_file = meta.get("source_file")
                source_type = meta.get("source_type", payload.get("source_type"))
                if source_type is None and source_file:
                    source_type = "uploaded_document"
                document_id = meta.get("document_id", payload.get("document_id"))
                if document_id is None and tenant and source_file:
                    document_id = hashlib.sha256(f"{tenant}:{source_file}".encode("utf-8")).hexdigest()
                # Legacy LangChain points predate canonical chunk ordinal metadata.
                # They remain readable during EXPAND, but are treated as isolated
                # chunks (no invented neighbor relationship).
                chunk_index = meta.get("chunk_index", payload.get("chunk_index", 0))
                total_chunks = meta.get("total_chunks", payload.get("total_chunks", 1))
                if not all(v is not None for v in (text, chunk_id, tenant, source_type, document_id)):
                    continue
                meta.setdefault("evidence_level", payload.get("evidence_level") or "document")
                chunk = KnowledgeChunk(
                    chunk_id=str(chunk_id),
                    tenant_id=str(tenant),
                    text=str(text),
                    source_type=str(source_type),
                    document_id=str(document_id),
                    chunk_index=int(chunk_index),
                    total_chunks=int(total_chunks),
                    metadata=meta,
                )
            dense = dense_map.get(cid, 0.0)
            sparse = sparse_map.get(cid, 0.0)
            fused_score = 0.7 * dense + 0.3 * sparse
            fused.append(RetrievedAnnotation(chunk, dense, sparse, fused_score))
        expanded = self._expand_neighbors(
            sorted(fused, key=lambda r: r.fused_score, reverse=True)[:top_k_initial]
        )
        reranked = self._rerank(query, expanded)
        return reranked[:final_k]

    def _expand_neighbors(self, hits: list[RetrievedAnnotation]) -> list[RetrievedAnnotation]:
        out = list(hits)
        seen = {h.chunk.chunk_id for h in out}
        by_doc_idx = {(c.tenant_id, c.document_id, c.chunk_index): c for c in self._chunks.values()}
        for hit in hits:
            for idx in (hit.chunk.chunk_index - 1, hit.chunk.chunk_index + 1):
                neighbor = by_doc_idx.get((hit.chunk.tenant_id, hit.chunk.document_id, idx))
                if neighbor and neighbor.chunk_id not in seen:
                    seen.add(neighbor.chunk_id)
                    out.append(
                        RetrievedAnnotation(
                            neighbor, 0.0, 0.0, hit.fused_score * 0.65, role="neighbor"
                        )
                    )
        return out

    def _rerank(self, query: str, rows: list[RetrievedAnnotation]) -> list[RetrievedAnnotation]:
        terms = set(tokenize(query))
        reranked = []
        for row in rows:
            overlap = sum(1 for t in terms if t in row.chunk.text.lower())
            score = row.fused_score + overlap * 0.05
            reranked.append(
                RetrievedAnnotation(
                    row.chunk,
                    row.dense_score,
                    row.bm25_score,
                    row.fused_score,
                    round(score, 6),
                    row.role,
                )
            )
        return sorted(reranked, key=lambda r: r.rerank_score or r.fused_score, reverse=True)
