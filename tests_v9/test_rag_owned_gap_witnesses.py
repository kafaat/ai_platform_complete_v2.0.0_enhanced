"""Offline behavioral witnesses for REPORT3 RAG-03/04/11; no live RAG claim."""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest

from tests_v9.service_module import load_service_main

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/sahool-platform"))
pq = importlib.import_module("core.rag.production_qdrant")


def chunk(tenant="tenant-a", text="ري القمح", **meta):
    return pq.KnowledgeChunk(
        chunk_id="c-" + tenant,
        tenant_id=tenant,
        text=text,
        source_type="curated_reference" if tenant == "__global__" else "uploaded_document",
        document_id="d-" + tenant,
        chunk_index=0,
        total_chunks=1,
        metadata={
            "evidence_level": "document",
            "source_uri": "test://document",
            "source_revision": "fixture-v1",
            "publisher": "test",
            "license": "test",
            **meta,
        },
    )


@pytest.fixture
def rag():
    return load_service_main(
        str(ROOT / "services/rag-retrieval"), required_attrs=("_ensure_sparse_index", "search")
    )


class Store:
    vector_size = 4

    def __init__(self, chunks):
        self.rows = [(c.chunk_id, c.payload) for c in chunks]

    def scroll_payloads(self):
        return self.rows

    def collection_point_count(self):
        return len(self.rows)


def wire(rag, chunks):
    store = Store(chunks)
    rag._qdrant = store
    rag._retriever = pq.HybridQdrantRetriever(store)
    rag._sparse_ready = False
    rag._SPARSE_PAYLOAD_REVALIDATE_SECONDS = 0
    rag._SPARSE_REVALIDATE_SECONDS = 0
    return store


def test_rag03_general_reference_survives_local_scope():
    assert pq.matches_scope_filters(
        chunk("__global__"), {"crop": "wheat", "region": "YE", "field_id": "F1"}
    )


@pytest.mark.parametrize("tenant", ["tenant-a", "__seed_quarantine__"])
def test_rag03_missing_scope_is_not_a_tenant_or_quarantine_wildcard(tenant):
    assert not pq.matches_scope_filters(chunk(tenant), {"crop": "wheat"})


def test_rag03_explicit_reference_mismatch_and_source_type_stay_strict():
    assert not pq.matches_scope_filters(chunk("__global__", crop="maize"), {"crop": "wheat"})
    assert not pq.matches_scope_filters(chunk("__global__"), {"source_type": "uploaded_document"})


def matches(condition, metadata):
    """Minimal interpreter for only Qdrant filter nodes emitted by this contract."""
    if "must" in condition and not all(matches(c, metadata) for c in condition["must"]):
        return False
    if "should" in condition and not any(matches(c, metadata) for c in condition["should"]):
        return False
    if "key" in condition:
        value = metadata.get(condition["key"].removeprefix("metadata."))
        rule = condition["match"]
        return value in rule["any"] if "any" in rule else value == rule["value"]
    for operator in ("is_empty", "is_null"):
        if operator in condition:
            value = metadata.get(condition[operator]["key"].removeprefix("metadata."))
            return value is None or (operator == "is_empty" and value == [])
    return True


@pytest.mark.parametrize(
    "tenant,crop,expected",
    [
        ("__global__", None, True),
        ("__global__", [], True),
        ("__global__", "maize", False),
        ("tenant-a", "wheat", True),
        ("tenant-a", None, False),
        ("tenant-b", "wheat", False),
        ("__seed_quarantine__", "wheat", False),
    ],
)
def test_rag03_dense_and_sparse_scope_agree(tenant, crop, expected):
    client = pq.QdrantHttpClient("http://qdrant", "fixture", 4)
    captured = []
    client._request = lambda method, path, payload: captured.append(payload) or {"result": []}
    client.search([1, 0, 0, 0], tenant_id="tenant-a", filters={"crop": "wheat"})
    c = chunk(tenant, crop=crop)
    assert matches(captured[0]["filter"], c.payload["metadata"]) is expected
    sparse = pq.BM25Index()
    sparse.add(c)
    assert bool(sparse.search("القمح", tenant_id="tenant-a", filters={"crop": "wheat"})) is expected


@pytest.mark.parametrize("replacement", [chunk(text="حصاد الذرة"), chunk(crop="maize")])
def test_rag04_same_count_content_or_scope_change_refreshes_bm25(rag, replacement):
    store = wire(rag, [chunk()])
    rag._ensure_sparse_index()
    store.rows = [(replacement.chunk_id, replacement.payload)]
    rag._ensure_sparse_index()
    actual = rag._retriever._chunks[replacement.chunk_id]
    assert actual.text == replacement.text
    assert all(actual.metadata.get(k) == v for k, v in replacement.metadata.items())


def test_rag04_expired_refresh_failure_cannot_serve_stale(rag):
    store = wire(rag, [chunk()])
    rag._ensure_sparse_index()

    def unavailable():
        raise RuntimeError("qdrant unavailable")

    store.scroll_payloads = unavailable
    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        rag._ensure_sparse_index()
    assert not rag._sparse_ready


def test_rag04_snapshot_digest_includes_actual_text_and_scope():
    rows = [("one", chunk().payload)]
    first = pq.payload_snapshot_digest(rows)
    rows[0][1]["metadata"]["tenant_id"] = "other"
    assert pq.payload_snapshot_digest(rows) != first
    second = pq.payload_snapshot_digest(rows)
    rows[0][1]["page_content"] = "changed without updating claimed digest"
    assert pq.payload_snapshot_digest(rows) != second


def test_rag11_quarantine_only_is_not_ready(rag):
    wire(rag, [chunk("__seed_quarantine__")])
    with pytest.raises(ValueError, match="no active readable content"):
        rag._ensure_sparse_index()


def test_rag11_other_tenant_corpus_cannot_make_request_ready(rag):
    wire(rag, [chunk("tenant-b")])
    req = rag.SearchRequest(tenant_id="tenant-a", query="القمح")
    with pytest.raises(Exception) as exc:
        asyncio.run(rag.search(req, x_tenant_id="tenant-a"))
    assert exc.value.status_code == 503
    assert "tenant has no active readable corpus" in exc.value.detail


def test_rag11_global_and_own_content_count_but_quarantine_does_not():
    store = Store([chunk(), chunk("tenant-b"), chunk("__global__"), chunk("__seed_quarantine__")])
    report = pq.HybridQdrantRetriever(store).rebuild_sparse_index()
    assert pq.visible_corpus_count(report, "tenant-a") == 2
    assert pq.visible_corpus_count(report, "new-tenant") == 1
    assert pq.visible_corpus_count(report, "__seed_quarantine__") == 0
