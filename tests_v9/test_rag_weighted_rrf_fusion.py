"""RAG fusion uses ranks, not incomparable raw dense/BM25 score magnitudes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"


def _module():
    spec = importlib.util.spec_from_file_location("_rrf_subject", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_rrf_subject"] = module
    spec.loader.exec_module(module)
    return module


m = _module()


def _reference_metadata():
    return {
        "source_uri": "sahool://reference",
        "source_revision": "r1",
        "publisher": "test",
        "license": "test-only",
        "jurisdiction": "YE",
        "language": "ar",
        "evidence_level": "document",
    }


def test_weighted_rrf_is_invariant_to_score_scale():
    dense = {"z": 0.9, "a": 0.4, "b": 0.1}
    sparse = {"a": 18.0, "z": 4.0, "c": 1.0}
    baseline, dense_ranks, sparse_ranks = m.weighted_rrf_scores(dense, sparse)
    scaled, scaled_dense_ranks, scaled_sparse_ranks = m.weighted_rrf_scores(
        {key: value * 1_000_000 for key, value in dense.items()},
        {key: value * 0.001 for key, value in sparse.items()},
    )

    assert baseline == scaled
    assert dense_ranks == scaled_dense_ranks
    assert sparse_ranks == scaled_sparse_ranks


def test_weighted_rrf_breaks_raw_score_ties_by_logical_id():
    _scores, dense_ranks, sparse_ranks = m.weighted_rrf_scores(
        {"z": 0.5, "a": 0.5}, {"y": 2.0, "b": 2.0}
    )

    assert dense_ranks == {"a": 1, "z": 2}
    assert sparse_ranks == {"b": 1, "y": 2}


def test_weighted_rrf_keeps_a_candidate_when_one_leg_is_missing():
    scores, dense_ranks, sparse_ranks = m.weighted_rrf_scores(
        {"dense-only": 0.7}, {"sparse-only": 10.0}
    )

    assert set(scores) == {"dense-only", "sparse-only"}
    assert dense_ranks == {"dense-only": 1}
    assert sparse_ranks == {"sparse-only": 1}
    assert scores["dense-only"] > scores["sparse-only"]


def test_annotation_declares_fusion_method_ranks_and_raw_diagnostics():
    chunk = m.KnowledgeChunk(
        chunk_id="chunk-1",
        tenant_id="tenant-a",
        text="FAO irrigation reference",
        source_type="reference_document",
        document_id="doc-1",
        chunk_index=0,
        total_chunks=1,
        metadata=_reference_metadata(),
    )
    annotation = m.RetrievedAnnotation(
        chunk,
        dense_score=0.8,
        bm25_score=12.0,
        fused_score=0.02,
        dense_rank=1,
        bm25_rank=2,
    ).as_annotation()

    assert annotation["decision_authority"] == "none"
    assert annotation["retrieval"] == {
        "dense_score": 0.8,
        "bm25_score": 12.0,
        "fused_score": 0.02,
        "rerank_score": None,
        "dense_rank": 1,
        "bm25_rank": 2,
        "fusion_method": "weighted_rrf",
        "fusion_version": "weighted_rrf_v1",
    }


def test_a_missing_retrieval_leg_is_not_reported_as_a_measured_zero():
    chunk = m.KnowledgeChunk(
        chunk_id="dense-only",
        tenant_id="tenant-a",
        text="reference",
        source_type="reference_document",
        document_id="doc-1",
        chunk_index=0,
        total_chunks=1,
        metadata=_reference_metadata(),
    )

    retrieval = m.RetrievedAnnotation(
        chunk=chunk,
        dense_score=0.8,
        bm25_score=None,
        fused_score=0.01,
        dense_rank=1,
        bm25_rank=None,
    ).as_annotation()["retrieval"]

    assert retrieval["dense_score"] == 0.8
    assert retrieval["bm25_score"] is None
    assert retrieval["bm25_rank"] is None


def test_retriever_preserves_an_absent_sparse_leg_as_absent():
    chunk = m.KnowledgeChunk(
        chunk_id="dense-only",
        tenant_id="tenant-a",
        text="reference",
        source_type="reference_document",
        document_id="doc-1",
        chunk_index=0,
        total_chunks=1,
        metadata=_reference_metadata(),
    )

    class DenseOnlyQdrant:
        vector_size = 1

        def search(self, *_args, **_kwargs):
            return [("storage-id", 0.8, chunk.payload)]

    class Embeddings:
        def embed(self, _text):
            return [1.0]

    class EmptySparseIndex:
        def search(self, *_args, **_kwargs):
            return []

    rows = m.HybridQdrantRetriever(
        DenseOnlyQdrant(), embeddings=Embeddings(), bm25=EmptySparseIndex()
    ).retrieve("reference", tenant_id="tenant-a")

    assert len(rows) == 1
    assert rows[0].dense_score == 0.8
    assert rows[0].bm25_score is None
    assert rows[0].bm25_rank is None
