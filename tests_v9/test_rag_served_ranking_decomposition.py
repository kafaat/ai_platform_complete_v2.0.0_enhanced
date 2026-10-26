"""REPORT3-RAG-08-01: a dense score is not the served ranking.

The canonical retriever serves the order produced by weighted RRF, neighbour
expansion and lexical-overlap rerank. A reader who compares ``dense_score`` with
the served order is measuring the wrong thing; the served order is carried by the
annotation ``score`` (rerank, else fused) and the per-stage ranks.

The defect fixed here: a neighbour admitted by expansion was never scored by the
dense or BM25 leg, yet it was served with ``dense_score == 0.0`` and
``bm25_score == 0.0``. Those read as measured zeros (a cosine of 0.0 is a valid
measurement) and made a dense score appear to contradict the served order. An
absent leg is reported as absent, as already required for a missing sparse leg in
``test_rag_weighted_rrf_fusion.py``.

These are unit witnesses of the serving contract, not retrieval-quality evidence.
The live per-stage measurement required by the gap's closure condition still
needs a Qdrant/Ollama stack.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"


def _module():
    spec = importlib.util.spec_from_file_location("_served_ranking_subject", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_served_ranking_subject"] = module
    spec.loader.exec_module(module)
    return module


m = _module()


def _chunk(chunk_id: str, text: str, *, document_id: str, chunk_index: int):
    return m.KnowledgeChunk(
        chunk_id=chunk_id,
        tenant_id="tenant-a",
        text=text,
        source_type="reference_document",
        document_id=document_id,
        chunk_index=chunk_index,
        total_chunks=2,
        metadata={
            "source_uri": "sahool://reference",
            "source_revision": "r1",
            "publisher": "test",
            "license": "test-only",
            "jurisdiction": "YE",
            "language": "ar",
            "evidence_level": "document",
        },
    )


# Dense prefers A; BM25 and lexical overlap prefer B; N is A's neighbour and is
# never returned by either leg.
A = _chunk("a", "wheat salinity", document_id="doc-1", chunk_index=0)
N = _chunk("n", "irrigation interval", document_id="doc-1", chunk_index=1)
B = _chunk("b", "wheat irrigation schedule", document_id="doc-2", chunk_index=0)


class _Qdrant:
    vector_size = 1

    def search(self, *_args, **_kwargs):
        return [("storage-a", 0.9, A.payload), ("storage-b", 0.5, B.payload)]


class _Embeddings:
    def embed(self, _text):
        return [1.0]


class _Sparse:
    def search(self, *_args, **_kwargs):
        return [(B, 12.0)]


def _serve():
    retriever = m.HybridQdrantRetriever(_Qdrant(), embeddings=_Embeddings(), bm25=_Sparse())
    # N is known to the retriever (as after sparse hydration) but is not a hit.
    retriever._chunks[N.chunk_id] = N
    return retriever.retrieve("irrigation", tenant_id="tenant-a", final_k=5)


def test_a_served_neighbour_carries_no_fabricated_dense_or_sparse_score():
    rows = _serve()
    neighbours = [r for r in rows if r.role == "neighbor"]
    assert [r.chunk.chunk_id for r in neighbours] == ["n"]

    retrieval = neighbours[0].as_annotation()["retrieval"]
    assert retrieval["dense_score"] is None
    assert retrieval["bm25_score"] is None
    assert retrieval["dense_rank"] is None
    assert retrieval["bm25_rank"] is None


def test_served_order_follows_the_annotation_score_not_the_dense_score():
    rows = _serve()
    served = [r.chunk.chunk_id for r in rows]
    dense_order = [
        r.chunk.chunk_id
        for r in sorted(
            (r for r in rows if r.dense_score is not None), key=lambda r: -r.dense_score
        )
    ]

    # Positive witness that the stages really disagree on this fixture.
    assert dense_order == ["a", "b"]
    assert served == ["b", "n", "a"]

    scores = [r.as_annotation()["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    # Only rows that the dense leg actually returned carry a dense rank.
    assert {r.chunk.chunk_id: r.dense_rank for r in rows} == {"b": 2, "n": None, "a": 1}
